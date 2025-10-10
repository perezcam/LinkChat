import logging
import queue
import threading
import time
from typing import Callable, Dict
from src.core.helpers.frame_creator import create_ethernet_frame
from src.core.managers.raw_socket import SocketManager
from src.core.enums.enums import MessageType
from src.core.helpers.frame_decoder import decode_ethernet_frame
from src.core.schemas.frame_schemas import FrameSchema
from src.core.schemas.scheduled_task import ScheduledTask
from src.file_transfer.handlers.file_transfer_handler import FileTransferHandler
from src.file_transfer.schemas.send_ctx import FileSendCtxSchema
from src.security.security_manager import SecurityManager

class ThreadManager:
    """
    Orquesta los hilos de trabajo para la aplicación de chat.
    Gestiona la recepción, el envío, el procesamiento de mensajes y las tareas periódicas.
    """
    def __init__(self, socket_manager: SocketManager, file_transfer_handler : FileTransferHandler, security: SecurityManager):
        self._socket_manager = socket_manager
        self._started = False
        self._incoming_queue: queue.Queue[FrameSchema] = queue.Queue()
        self._outgoing_queue: queue.Queue[FrameSchema] = queue.Queue()
        self._shutdown_event = threading.Event()
        self.file_transfer_handler = file_transfer_handler
        self.security = security

        self._message_handlers: Dict[MessageType, Callable[[FrameSchema], None]] = {}
        self._scheduled_tasks: list[ScheduledTask] = []

        self._ctx_by_id: Dict[str, FileSendCtxSchema] = {}


        self.receiver =     threading.Thread(target=self._receiver_loop,    name="receiver",    daemon=True)
        self.sender =       threading.Thread(target=self._sender_loop,      name="sender",      daemon=True)
        self.scheduler =    threading.Thread(target=self._scheduler_loop,   name="scheduler",   daemon=True)
        self.dispatcher =   threading.Thread(target=self._dispatcher_loop,  name="dispatcher",  daemon=True)
        self.file_sender_thread =  threading.Thread(target=self._file_sender_loop, name="file_sender", daemon=True)

        self.threads = [self.receiver, self.sender, self.scheduler, self.dispatcher, self.file_sender_thread]


    def _receiver_loop(self):
        """Recibe mensajes y los pone en la incoming_queue."""
        logging.info("[Receiver] Hilo iniciado.")
        while not self._shutdown_event.is_set():
            try:
                frame_bytes = self._socket_manager.receive_raw_frame()
                if not frame_bytes:
                    continue

                try:
                    decoded_frame = decode_ethernet_frame(frame_bytes)
                except ValueError as e:
                    # Tip: ValueError lo usamos cuando el CRC no coincide (frame corrupto)
                    logging.warning(f"[Receiver] Frame descartado (CRC inválido): {e}")
                    continue  # no encolar

                if decoded_frame is None:
                    # Tip: Si tu decoder devuelve None para tipos/ethertype ajenos, simplemente ignora
                    continue

                if self.security:
                    decoded_frame = self.security.accept_incoming(decoded_frame)
                    if decoded_frame is None:
                        continue

                self._incoming_queue.put(decoded_frame)

            except Exception as e:
                logging.error(f"[Receiver] Error: {e}")
                time.sleep(1)  # Evitar un bucle de error muy rápido

    def _sender_loop(self):
        """Despacha mensajes desde la outgoing_queue."""
        logging.info("[Sender] Hilo iniciado.")
        while not self._shutdown_event.is_set():
            try:
                frame_to_send = self._outgoing_queue.get(timeout=1)

                if self.security:
                    frame_to_send = self.security.protect_outgoing(frame_to_send)

                frame_to_send_bytes = create_ethernet_frame(frame_to_send)
                self._socket_manager.send_raw_frame(frame_to_send_bytes)
                self._outgoing_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"[Sender] Error: {e}")

    def _scheduler_loop(self):
        logging.info("[Scheduler] Hilo iniciado.")
        
        while not self._shutdown_event.is_set():
            current_time = time.time()
            
            for task in self._scheduled_tasks:
                if current_time - task.last_run >= task.interval:
                    try:
                        logging.info(f"[Scheduler] Ejecutando tarea periódica: {task.action.__name__}")
                        task.action()
                        
                        task.last_run = current_time
                    except Exception as e:
                        logging.error(f"[Scheduler] Error ejecutando la tarea {task.action.__name__}: {e}")

            # Espera un poco para no consumir 100% de CPU.
            self._shutdown_event.wait(timeout=1)
        

    def _dispatcher_loop(self):
        """Procesa mensajes de la incoming_queue."""
        logging.info("[Dispatcher] Hilo iniciado.")
        while not self._shutdown_event.is_set():
            try:
                received_frame = self._incoming_queue.get(timeout=1)
                
                handler = self._message_handlers.get(received_frame.header.message_type)
                if handler:
                    handler(received_frame)
                else:
                    logging.info(f"[Dispatcher] No se encontró manejador para el tipo de mensaje: {received_frame.header.message_type}")
                
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"[Dispatcher] Error: {e}")


    def _file_sender_loop(self):
        """Rellena ventana, retransmite chunks perdidos, finaliza si aplica """
        while not self._shutdown_event.is_set():     
            self._pump()  
            time.sleep(0.02)  

    def _pump(self):
        now = time.time()
        for ctx in list(self._ctx_by_id.values()):
            if ctx.finished:
                self._ctx_by_id.pop(ctx.file_id)
                continue
            if ctx.meta_acked:
                with ctx.lock:
                    self._retransfer_expired(ctx, now)

                    if not ctx.finished:
                        self._refill_window(ctx)
            
            # Completado
            if ctx.last_acked + 1 >= ctx.total_chunks and not ctx.finished:
                frame: FrameSchema = self.file_transfer_handler.get_file_fin_frame(ctx, status="ok")
                self.queue_frame_for_sending(frame)
                with ctx.lock:
                    ctx.finished = True     
                logging.debug("[TX] complete window file_id=%s last_acked=%d total=%d", ctx.file_id, ctx.last_acked, ctx.total_chunks)

    def _mark_inflight(self, ctx : FileSendCtxSchema, idx: int, retries: int = 0) :
        ctx.inflight[idx] = (time.time(), retries) 

    def _retransfer_expired(self, ctx: FileSendCtxSchema, now: float):
        # 1) Retransmitir vencidos
        for idx, (last_time, retries) in list(ctx.inflight.items()):
            if now - last_time >= ctx.timeout_s:
                if retries >= ctx.max_retries:
                    frame : FrameSchema = self.file_transfer_handler.get_file_fin_frame(
                        ctx, 
                        status="error", 
                        reason="timeout"
                    )
                    logging.debug(
                        "[RTX] retransmit idx=%d file_id=%s retry=%d timeout=%.2fs",
                        idx, ctx.file_id, retries + 1, ctx.timeout_s
                    )
                    self.queue_frame_for_sending(frame)
                    ctx.finished = True
                    break
                frame : FrameSchema = self.file_transfer_handler.get_data_chunk(ctx, idx)
                self.queue_frame_for_sending(frame)
                self._mark_inflight(ctx, idx, retries=retries+1)
                logging.debug(
                    "[RTX] retransmit idx=%d file_id=%s retry=%d timeout=%.2fs",
                    idx, ctx.file_id, retries + 1, ctx.timeout_s
                )

    def _refill_window(self, ctx: FileSendCtxSchema):
        while len(ctx.inflight) < ctx.window_size and ctx.next_to_send < ctx.total_chunks:
            idx = ctx.next_to_send
            frame : FrameSchema = self.file_transfer_handler.get_data_chunk(ctx, idx)

            logging.debug(
                "[TX] send chunk idx=%d file_id=%s win=%d inflight=%d next_to_send->%d",
                idx, ctx.file_id, ctx.window_size, len(ctx.inflight), ctx.next_to_send + 1
            )

            self.queue_frame_for_sending(frame)
            self._mark_inflight(ctx, idx)
            ctx.next_to_send += 1


    def start(self):
        if self._started:
            return
        self._started = True
        for thread in self.threads:
            thread.start()

    def stop(self):
        self._shutdown_event.set()

        for thread in self.threads:
            thread.join()

    @property
    def src_mac(self) -> str | None:
        return getattr(self._socket_manager, "mac", None)
    
    def queue_frame_for_sending(self, frame: FrameSchema):
        self._outgoing_queue.put(frame)

    def add_message_handler(self, msg_type: MessageType, f: Callable[[FrameSchema], None]):
        self._message_handlers[msg_type] = f

    def remove_message_handler(self, msg_type: MessageType):
        self._message_handlers.pop(msg_type, None)

    def add_scheduled_task(self, task: ScheduledTask):
        self._scheduled_tasks.append(task)

    def remove_scheduled_task(self, action: Callable[[], None]):
        self._scheduled_tasks = [
            t for t in self._scheduled_tasks if t.action is not action
        ]

    def add_ctx_by_id(self, id: str, ctx: FileSendCtxSchema):
        self._ctx_by_id[id] = ctx 

    def get_ctx_by_id(self, id: str) -> FileSendCtxSchema | None:
        return self._ctx_by_id.get(id)