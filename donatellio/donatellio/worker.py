import asyncio
import json
from donatellio.redisstream import RedisPayload, RedisStream
from donatellio.workers.image import generate_image


async def mainloop():
    stream = RedisStream("image-jobs")
    completed_stream = RedisStream("completed-jobs")
    await stream.setup_group(new_only=False)
    while True:
        response = await stream.consume_msg("consumer2", new_only=True, n_msgs=10)
        if response.messages == []:
            print("No messages available")
            await asyncio.sleep(2)
        for msg in response.messages:
            print("got a message")
            params = json.loads(msg.json.payload)
            if msg.json.function_name == "generate_image":
                filepath = generate_image(**params)
            else:
                raise RuntimeError(f"Unknown function: {msg.json.function_name}")
                
            await stream.ack_msg(msg.id)
            await completed_stream.send_msg(RedisPayload(msg.json.job_id, msg.json.function_name, {"image_url": filepath}))
            print(f"Processed message with ID: {msg.id}")
    
if __name__ == "__main__":
    asyncio.run(mainloop())