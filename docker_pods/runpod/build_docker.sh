DOCKERTAG=$1

sudo docker build --platform linux/amd64 -t musegim/hunyuan3d:${DOCKERTAG} .

# testing (need to copy test_input.json for this to work)
sudo docker run --gpus all -it musegim/hunyuan3d:${DOCKERTAG}

sudo docker push musegim/hunyuan3d:${DOCKERTAG}