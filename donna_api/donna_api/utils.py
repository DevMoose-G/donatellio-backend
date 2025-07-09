mesh_quality_multiplier = {"low": 2, "medium": 3, "high": 4}

texture_quality_multiplier = {"normal": 3, "precise": 5, "stylized": 4}

regen_mesh_cost = 2

def image_cost(image_model, quality) -> int:
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
    
    return cost

def calculate_mesh_gen_cost(n_meshes, quality, labels):
    quality_multiplier = mesh_quality_multiplier[quality]
    cost = (n_meshes * quality_multiplier) + len(labels)
    return cost


def calculate_texture_gen_cost(prompt, texture_quality):
    quality_multiplier = texture_quality_multiplier[texture_quality]
    cost = quality_multiplier
    return cost