from typing import List

from pydantic import TypeAdapter
from redis.asyncio import Redis

from donna_common.redis.types import Action, BaseAction, RedisMessage

r = Redis(host="localhost", port=6379, decode_responses=True)


class RedisStream:
    def __init__(self, stream_key, group_name="default"):
        self.stream_key = stream_key
        self.group_name = group_name

    # part of the consumer setup
    async def setup_group(self, new_only=False):
        group_names = []
        try:
            groups = await r.xinfo_groups(self.stream_key)
            group_names = [g["name"] for g in groups]
        except:
            print("No groups found. Redis key may not exist.")
        if self.group_name not in group_names:
            # $ means only read from this point onwards
            await r.xgroup_create(
                self.stream_key,
                self.group_name,
                "$" if new_only else "0",
                mkstream=True,
            )

    # returns the message id
    async def send_msg(self, action: BaseAction) -> int:
        return await r.xadd(
            self.stream_key,
            {
                "data": action.model_dump_json().encode("utf-8")
                # "function_name": payload.function_name,
                # "project_id": payload.project_id,
                # "type": payload_dc.__name__,
                # "payload": json.dumps(
                #     payload
                # ),  # temporary (find some way to auto convert to JSON)
            },
        )

    async def consume_msg(
        self, consumer_name, new_only=True, n_msgs=1
    ) -> List[RedisMessage]:
        # 0-0 only gets messages that are already pending (delivered but not acknowledged)
        # > gets messages that have not been delivered to any consumer
        entries = await r.xreadgroup(
            self.group_name,
            consumer_name,
            {self.stream_key: ">" if new_only else "0"},
            count=n_msgs,
            block=5000,
        )
        if len(entries) == 0:
            return []
            # return RedisReadResponse(self.stream_key, [])
        messages = []
        for _, msgs in entries:
            for _id, fields in msgs:
                action = TypeAdapter(Action).validate_json(fields["data"])
                messages.append(RedisMessage(id=_id, action=action))
                # msgs.append(RedisMessage(msg[0], RedisPayload(**msg[1])))
        return messages

    async def ack_msg(self, msg_id):
        await r.xack(self.stream_key, self.group_name, msg_id)
