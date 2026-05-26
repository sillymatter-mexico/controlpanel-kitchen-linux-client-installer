"""Declarative process registry for the CPK agent service.

Each ``ProcessSpec`` entry is the single source of truth for a background
process.  Both the dev supervisor and the systemd installer consume this list,
so adding a new worker only requires appending one entry here.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProcessSpec:
    """Description of a managed background process.

    Attributes:
        name: Short identifier used as the systemd unit name
              (e.g. ``"cpk-ws-listener"`` → ``cpk-ws-listener.service``).
        module: Fully-qualified Python module that serves as the entry point.
                Run with ``python -m <module>``.
        description: Human-readable description written into the systemd
                     ``Description=`` field and shown in logs.
        restart_delay: Seconds to wait before restarting a crashed process in
                       the dev supervisor (initial delay; backoff is applied on
                       top of this by the supervisor).
    """

    name: str
    module: str
    description: str
    restart_delay: float = field(default=2.0)


#: All processes managed by the agent service.
#: The dev supervisor and the systemd installer iterate over this list.
REGISTRY: list[ProcessSpec] = [
    ProcessSpec(
        name="cpk-ws-listener",
        module="services.agent.listener",
        description="CPK WebSocket listener — receives server events and enqueues tasks",
    ),
    ProcessSpec(
        name="cpk-print-worker",
        module="services.agent.workers.print_worker",
        description="CPK print worker — dequeues print tasks and submits jobs to CUPS",
    ),
    ProcessSpec(
        name="cpk-tts-worker",
        module="services.agent.workers.tts_worker",
        description="CPK TTS worker — dequeues TTS tasks and plays audio serially",
    ),
]
