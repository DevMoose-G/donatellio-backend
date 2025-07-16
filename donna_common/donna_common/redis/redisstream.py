from typing import List

from pydantic import TypeAdapter
from redis.asyncio import Redis

from donna_common.redis.types import Action, BaseAction, ImageAction, JobUpdate, MeshAction, RedisMessage, TexturedMeshAction
from donna_common.settings import settings

redis = Redis.from_url(settings.redis_url, decode_responses=True)

class RedisStream:
    def __init__(self, stream_key, group_name="default"):
        self.stream_key = stream_key
        self.group_name = group_name

    # part of the consumer setup
    async def setup_group(self, new_only=False):
        group_names = []
        try:
            groups = await redis.xinfo_groups(self.stream_key)
            group_names = [g["name"] for g in groups]
        except:
            print("No groups found. Redis key may not exist.")
        if self.group_name not in group_names:
            # $ means only read from this point onwards
            await redis.xgroup_create(
                self.stream_key,
                self.group_name,
                "$" if new_only else "0",
                mkstream=True,
            )

    # returns the message id
    async def send_msg(self, action: BaseAction) -> int:
        message_id = await redis.xadd(
            self.stream_key,
            {
                "data": action.model_dump_json().encode("utf-8")
            },
        )
        
        # redis.set(f"job:{message_id}", JobUpdate(
        #     job_id=message_id,
        #     status="pending",
        #     message="Starting job"
        # ).model_dump_json())
        # if action.type == "image":
        #     action: ImageAction = TypeAdapter(ImageAction).validate_python(action)
        #     # For image actions, we also add it to the image stream
        #     await redis.zadd(f"jobs_by_image_id:{action.image_id}", mapping={message_id: action.timestamp.timestamp()})
        # elif action.type == "mesh":
        #     action: MeshAction = TypeAdapter(MeshAction).validate_python(action)
        #     # For mesh actions, we also add it to the mesh stream
        #     await redis.zadd(f"jobs_by_mesh_id:{action.mesh_id}", mapping={message_id: action.timestamp.timestamp()})
        # elif action.type == "textured_mesh":
        #     action: TexturedMeshAction = TypeAdapter(TexturedMeshAction).validate_python(action)
        #     # For textured mesh actions, we also add it to the textured mesh stream
        #     await redis.zadd(f"jobs_by_texture_id:{action.texture_id}", mapping={message_id: action.timestamp.timestamp()})
        
        return message_id
    
    async def update_job_status(self, job_id: str, status: str, message: str = None):
        job_update = JobUpdate(
            job_id=job_id,
            status=status,
            message=message
        )
        await redis.set(f"job:{job_id}", job_update.model_dump_json())
    
    async def get_jobs_by_image_id(self, image_id: str, limit: int = 10) -> List[RedisMessage]:
        messages = await redis.zrange(
            f"jobs_by_image_id:{image_id}",
            0,
            limit - 1,
            withscores=True
        )
        return [RedisMessage(id=msg_id, action=TypeAdapter(Action).validate_json(msg_data)) for msg_id, msg_data in messages]
    
    async def get_jobs_by_mesh_id(self, mesh_id: str, limit: int = 10) -> List[RedisMessage]:
        messages = await redis.zrange(
            f"jobs_by_mesh_id:{mesh_id}",
            0,
            limit - 1,
            withscores=True
        )
        return [RedisMessage(id=msg_id, action=TypeAdapter(Action).validate_json(msg_data)) for msg_id, msg_data in messages]

    async def get_jobs_by_texture_id(self, texture_id: str, limit: int = 10) -> List[RedisMessage]:
        messages = await redis.zrange(
            f"jobs_by_texture_id:{texture_id}",
            0,
            limit - 1,
            withscores=True
        )
        return [RedisMessage(id=msg_id, action=TypeAdapter(Action).validate_json(msg_data)) for msg_id, msg_data in messages]

    async def consume_msg(
        self, consumer_name, new_only=True, n_msgs=1
    ) -> List[RedisMessage]:
        # 0-0 only gets messages that are already pending (delivered but not acknowledged)
        # > gets messages that have not been delivered to any consumer
        entries = await redis.xreadgroup(
            self.group_name,
            consumer_name,
            {self.stream_key: ">" if new_only else "0"},
            count=n_msgs,
            block=5000,
        )
        if len(entries) == 0:
            return []
        messages = []
        for _, msgs in entries:
            for _id, fields in msgs:
                try:
                    fields["data"]
                except KeyError:
                    raise Exception(str(fields))
                action = TypeAdapter(Action).validate_json(fields["data"])
                messages.append(RedisMessage(id=_id, action=action))
        return messages

    async def ack_msg(self, msg_id):
        await redis.xack(self.stream_key, self.group_name, msg_id)
