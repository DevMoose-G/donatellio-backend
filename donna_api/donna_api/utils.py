mesh_quality_multiplier = {"low": 2, "medium": 3, "high": 4}

texture_quality_multiplier = {"normal": 3, "precise": 5, "stylized": 4}

regen_mesh_cost = 2

valid_image_models = ["gpt4o", "fluxkontext", "imagen4"]

def image_cost(image_model, quality, has_style_image=False) -> int:
    if image_model not in valid_image_models:
        raise ValueError(f"Invalid image model: {image_model}. Valid models are: {valid_image_models}")
    if image_model == "gpt4o":
        if quality == "high":
            cost = 3
        elif quality == "medium":
            cost = 2
        elif quality == "low":
            cost = 1
    elif image_model == "fluxkontext":
        if quality == "high":
            cost = 2
        elif quality == "medium":
            cost = 1
        elif quality == "low":
            cost = 1
    elif image_model == "imagen4":
        cost = 1

    if has_style_image:
        cost += 1

    return cost


def calculate_mesh_gen_cost(n_meshes, quality, labels):
    quality_multiplier = mesh_quality_multiplier[quality]
    cost = (n_meshes * quality_multiplier) + len(labels)
    return cost


def calculate_texture_gen_cost(texture_quality):
    quality_multiplier = texture_quality_multiplier[texture_quality]
    cost = quality_multiplier
    return cost


def expected_mesh_gen_time(quality):
    if quality == "low":
        time = 45
    elif quality == "medium":
        time = 65
    elif quality == "high":
        time = 80

    return time


def expected_texture_gen_time(texture_quality):
    if texture_quality == "normal":
        time = 60
    elif texture_quality == "precise":
        time = 85
    elif texture_quality == "stylized":
        time = 65

    return time
