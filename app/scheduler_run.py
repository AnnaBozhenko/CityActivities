from taskiq import TaskiqScheduler
from main import broker
from taskiq.schedule_sources import LabelScheduleSource

import worker

schedule_source = LabelScheduleSource(broker=broker)
scheduler = TaskiqScheduler(
    broker, 
    sources=[schedule_source]
)
