import asyncio
import json
from donatellio.redisstream import RedisPayload, RedisStream
from donatellio.workers.image import generate_image, get_elaborating_questions


async def mainloop():
    stream = RedisStream("image-jobs")
    completed_stream = RedisStream("completed-jobs")
    await stream.setup_group(new_only=False)
    while True:
        response = await stream.consume_msg("consumer", new_only=True, n_msgs=10)
        if response.messages == []:
            print("No messages available")
            await asyncio.sleep(2)
        for msg in response.messages:
            print("got a message")
            params = json.loads(msg.json.payload)
            if msg.json.function_name == "generate_image":
                filepath = generate_image(**params)
                await completed_stream.send_msg(RedisPayload(msg.json.project_id, msg.json.function_name, {"image_url": filepath}))
            elif msg.json.function_name == "get_elaborating_questions":
                questions = get_elaborating_questions(**params)
                breakpoint() # untested
                await completed_stream.send_msg(RedisPayload(msg.json.project_id, msg.json.function_name, {"questions": questions}))
            else:
                raise RuntimeError(f"Unknown function: {msg.json.function_name}")
                
            await stream.ack_msg(msg.id)
            
            print(f"Processed message with ID: {msg.id}")
    
if __name__ == "__main__":
    asyncio.run(mainloop())