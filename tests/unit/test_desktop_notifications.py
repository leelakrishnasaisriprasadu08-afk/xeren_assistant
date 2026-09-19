"""Unit tests for DesktopNotifier and notification event dispatching."""

import pytest
from desktop.notifications import DesktopNotifier, NotificationEvent, NotificationLevel


def test_desktop_notifier_event_creation_and_history():
  notifier = DesktopNotifier(enabled=False)  # Disable OS popups during testing

  event = notifier.notify(
      title="Task Completed",
      message="Background backup job succeeded.",
      level=NotificationLevel.SUCCESS,
      channel="scheduler",
  )

  assert event.title == "Task Completed"
  assert event.level == NotificationLevel.SUCCESS
  assert event.channel == "scheduler"

  history = notifier.get_history(limit=10)
  assert len(history) >= 1
  assert history[0].title == "Task Completed"


def test_desktop_notifier_listeners():
  notifier = DesktopNotifier(enabled=False)
  received_events = []

  def listener(evt: NotificationEvent):
    received_events.append(evt)

  notifier.register_listener(listener)

  notifier.notify(title="Swarm Consensus", message="Coder approved.")
  assert len(received_events) == 1
  assert received_events[0].title == "Swarm Consensus"


@pytest.mark.asyncio
async def test_desktop_notifier_async():
  notifier = DesktopNotifier(enabled=False)
  event = await notifier.notify_async(
      title="Async Event", message="Non-blocking notification"
  )
  assert event.title == "Async Event"
