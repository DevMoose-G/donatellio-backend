FROM rupintalwar/hunyuan3d:latest

WORKDIR /app/Hunyuan3D-2

# TODO: include model files directly in Docker image to ensure faster startup times and more reliable execution.

RUN pip install -r requirements.txt
RUN pip install -e .

WORKDIR /
COPY builder/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/handler.py .
COPY test_input.json .

# Default command
CMD ["python3", "-u", "/handler.py"]
