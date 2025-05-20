FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

# COPY MODEL WEIGHTS (FOR PRODUCTION)

# Install Python & GIT
RUN apt-get update && \
    apt-get install -y python3-pip python3-dev python3-venv git && \
    rm -rf /var/lib/apt/lists/*

# Install system packages Pillow needs to build JPEG/PNG/etc support
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      libjpeg-dev \
      zlib1g-dev \
      libpng-dev \
      libtiff-dev \
      libfreetype6-dev \
      libgl1 \
      pybind11-dev \
      pkg-config \
 && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /.venv/
ENV PATH="/.venv/bin:$PATH"
RUN pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
RUN pip install torch-cluster -f https://data.pyg.org/whl/torch-2.5.1+cu124.html

ENV ON_RUNPOD=True
ENV TORCH_CUDA_ARCH_LIST="8.0+PTX;8.6+PTX;8.9+PTX"

COPY ./step1x-3d-geometry /app/step1x-3d-geometry
WORKDIR /app/
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      build-essential \
      cmake \
      ninja-build \
      python3-dev && \
    rm -rf /var/lib/apt/lists/*
RUN pip install ninja cmake
RUN pip install --editable ./step1x-3d-geometry


COPY builder/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY test_input.json /app/test_input.json

COPY handler.py /app/handler.py

CMD ["python", "-u", "handler.py"]