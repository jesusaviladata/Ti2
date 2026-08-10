"""APScheduler instance shared across the app."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler(timezone="UTC")


def start():
    if not scheduler.running:
        scheduler.start()


def stop():
    if scheduler.running:
        scheduler.shutdown(wait=False)
