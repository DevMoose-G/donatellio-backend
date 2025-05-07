FROM python:3.10-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libgl1-mesa-glx build-essential git \
      libsm6 libxext6 libxrender1 libfontconfig1 \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir torch transformers fastapi uvicorn

# in future, prebuild with these dependencies above since they likely won't change

COPY handler.py /app/handler.py
COPY test.py /app/test.py

RUN git clone https://github.com/Tencent/Hunyuan3D-2.git /app/Hunyuan3D-2
WORKDIR /app/Hunyuan3D-2    
RUN pip install -r requirements.txt
RUN pip install -e .

WORKDIR /app

# Expose the port your app listens on:
EXPOSE 8000

# Default command
# CMD ["uvicorn", "handler:app", "--host", "0.0.0.0", "--port", "8000"]
ENTRYPOINT ["/bin/bash"]
