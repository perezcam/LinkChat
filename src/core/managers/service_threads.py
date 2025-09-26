
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

class ThreadManager:
    """
    Orquesta los hilos de trabajo para la aplicación de chat.
    Gestiona la recepción, el envío, el procesamiento de mensajes y las tareas periódicas.
    """
    def __init__(self, socket_manager: SocketManager):
        self.socket_manager = socket_manager

        self.incoming_queue: queue.Queue[FrameSchema] = queue.Queue()
        self.outgoing_queue: queue.Queue[FrameSchema] = queue.Queue()
        self.shutdown_event = threading.Event()

        self.message_handlers: Dict[MessageType, Callable[[FrameSchema], None]] = {
            # TODO: Añade aquí los manejadores para transferencia de archivos, etc.
            # O crea funciones que permitan agregar callables tanto al message handler como al scheduled_tasks
        }
        self.scheduled_tasks: list[ScheduledTask] = []


        self.receiver = threading.Thread(target=self._receiver_loop, name="receiver", daemon=True)
        self.sender = threading.Thread(target=self._sender_loop, name="sender", daemon=True)
        self.scheduler = threading.Thread(target=self._scheduler_loop, name="scheduler", daemon=True)
        self.dispatcher = threading.Thread(target=self._dispatcher_loop, name="dispatcher", daemon=True)

        self.threads = [self.receiver, self.sender, self.scheduler, self.dispatcher]


    def _receiver_loop(self):
        """Recibe mensajes y los pone en la incoming_queue."""
        logging.info("[Receiver] Hilo iniciado.")
        while not self.shutdown_event.is_set():
            try:
                frame_bytes = self.socket_manager.receive_raw_frame()
                if frame_bytes:
                    decoded_frame = decode_ethernet_frame(frame_bytes)
                    self.incoming_queue.put(decoded_frame)
            except Exception as e:
                logging.error(f"[Receiver] Error: {e}")
                time.sleep(1) # Evitar un bucle de error muy rápido

    def _sender_loop(self):
        """Despacha mensajes desde la outgoing_queue."""
        logging.info("[Sender] Hilo iniciado.")
        while not self.shutdown_event.is_set():
            try:
                frame_to_send = self.outgoing_queue.get(timeout=1)
                frame_to_send_bytes = create_ethernet_frame(frame_to_send)
                self.socket_manager.send_raw_frame(frame_to_send_bytes)
                self.outgoing_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"[Sender] Error: {e}")

    def _scheduler_loop(self):
        logging.info("[Scheduler] Hilo iniciado.")
        
        while not self.shutdown_event.is_set():
            current_time = time.time()
            
            for task in self.scheduled_tasks:
                if current_time - task.last_run >= task.interval:
                    try:
                        logging.info(f"[Scheduler] Ejecutando tarea periódica: {task.action.__name__}")
                        task.action()
                        
                        task.last_run = current_time
                    except Exception as e:
                        logging.error(f"[Scheduler] Error ejecutando la tarea {task.action.__name__}: {e}")

            # Espera un poco para no consumir 100% de CPU.
            self.shutdown_event.wait(timeout=1)
        

    def _dispatcher_loop(self):
        """Procesa mensajes de la incoming_queue."""
        logging.info("[Dispatcher] Hilo iniciado.")
        while not self.shutdown_event.is_set():
            try:
                received_frame = self.incoming_queue.get(timeout=1)
                
                handler = self.message_handlers.get(received_frame.header.message_type)
                if handler:
                    handler(received_frame)
                else:
                    logging.info(f"[Dispatcher] No se encontró manejador para el tipo de mensaje: {received_frame.header.message_type}")
                
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"[Dispatcher] Error: {e}")

    def start(self):
        for thread in self.threads:
            thread.start()

    def stop(self):
        self.shutdown_event.set()

        for thread in self.threads:
            thread.join()

    @property
    def src_mac(self) -> str | None:
        return getattr(self.socket_manager, "mac", None)
    
    def queue_frame_for_sending(self, frame: FrameSchema):
        self.outgoing_queue.put(frame)
