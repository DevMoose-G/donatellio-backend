from dataclasses import asdict, dataclass
import json
import time
from typing import List, Optional
from redis.asyncio import Redis

@dataclass
class RedisPayload:
    job_id: str
    function_name: str
    payload: dict

@dataclass
class RedisMessage:
    id: str
    json: RedisPayload

@dataclass
class RedisReadResponse:
    stream_key: str
    messages: List[RedisMessage]

r = Redis(host='localhost', port=6379, decode_responses=True)

class RedisStream:
    def __init__(self, stream_key, group_name="default"):
        self.stream_key = stream_key
        self.group_name = group_name

    async def setup_group(self, new_only=False):
        groups = await r.xinfo_groups(self.stream_key)
        group_names = [g["name"] for g in groups]
        if self.group_name not in group_names:
            # $ means only read from this point onwards
            await r.xgroup_create(self.stream_key, self.group_name, "$" if new_only else '0') 

    # returns the message id
    async def send_msg(self, payload: RedisPayload) -> int:
        return await r.xadd(
            self.stream_key,
            {
                "function_name": payload.function_name,
                "job_id": payload.job_id,
                "payload": json.dumps(payload.payload) # temporary (find some way to auto convert to JSON)
            },
        )

    async def consume_msg(self, consumer_name, new_only=True, n_msgs=1) -> RedisReadResponse:
        # 0-0 only gets messages that are already pending (delivered but not acknowledged)
        # > gets messages that have not been delivered to any consumer
        streams = await r.xreadgroup(self.group_name, consumer_name, {self.stream_key: ">" if new_only else '0'}, count=n_msgs, block=5000)
        if len(streams) == 0:
            return RedisReadResponse(self.stream_key, [])
            # return RedisReadResponse(self.stream_key, [])
        stream = streams[0]
        msgs = []
        for msg in stream[1]:
            msgs.append(RedisMessage(msg[0], RedisPayload(**msg[1])))
        return RedisReadResponse(stream[0], msgs)

    async def ack_msg(self, msg_id):
        await r.xack(self.stream_key, self.group_name, msg_id)