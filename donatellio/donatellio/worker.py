import asyncio
import json
from donatellio.workers.mesh import generate_mesh, generate_texture
from donatellio.redisstream import RedisPayload, RedisStream
from donatellio.workers.image import edit_image, generate_image, get_elaborating_questions


async def mainloop():
    stream = RedisStream("requested-jobs")
    completed_images_stream = RedisStream("completed-jobs", group_name="image")
    completed_meshes_stream = RedisStream("completed-jobs", group_name="mesh")
    await stream.setup_group(new_only=False)
    while True:
        response = await stream.consume_msg("consumer", new_only=True, n_msgs=10)
        if response.messages == []:
            print("No messages available")
            await asyncio.sleep(5)
        for msg in response.messages:
            print("got a message")
            params = json.loads(msg.json.payload)
            if msg.json.function_name == "generate_image":
                s3_key = await generate_image(**params)
                # await completed_images_stream.send_msg(RedisPayload(msg.json.project_id, msg.json.function_name, {"image_id": params['image_id']}))
            elif msg.json.function_name == "edit_image":
                s3_key = await edit_image(**params)
                await completed_images_stream.send_msg(RedisPayload(msg.json.project_id, msg.json.function_name, {"image_id": params['image_id']}))
            elif msg.json.function_name == "generate_mesh":
                mesh_ids = await generate_mesh(**params)
                await completed_meshes_stream.send_msg(RedisPayload(msg.json.project_id, msg.json.function_name, {"mesh_ids": mesh_ids}))
            elif msg.json.function_name == "generate_texture":
                mesh_id = await generate_texture(**params)
                await completed_meshes_stream.send_msg(RedisPayload(msg.json.project_id, msg.json.function_name, {"mesh_ids": [mesh_id]}))
            else:
                raise RuntimeError(f"Unknown function: {msg.json.function_name}")
                
            await stream.ack_msg(msg.id)
            
            print(f"Processed message with ID: {msg.id}")
    
if __name__ == "__main__":
    asyncio.run(mainloop())