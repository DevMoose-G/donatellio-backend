BASE_IMAGE_GEN_PROMPT = "Zoom out to include the whole image. Draw as a 3D model."
GPT4O_IMAGE_GEN_PROMPT = f"Don't put any background. Image has to be transparent. Remove any shadows and lighting outside of the image. {BASE_IMAGE_GEN_PROMPT}"
GEMINI_IMAGE_GEN_PROMPT = (
    f"Put a clear background of a color not used in the image. {BASE_IMAGE_GEN_PROMPT}"
)


# system prompts
ELABORATION_PROMPT = "You’re a 3D model assistant.\nAsk exactly {n_questions} follow-up questions to nail down the key details of the initial image.\nKeep each under six words, informal, no “who/what/where/etc.”\nReturn them as plain lines, no numbers. Focus on the image itself, not the 3D model or the background or environment."
CHECK_ELABORATION_PROMPT = "You’re a 3D model assistant.\nFrom the three questions below, remove any the user answered and return only the rest of the questions (unanswered).\nKeep each under six words, informal, no question words.\nList one per line, no numbering."

NAME_PROJECT_BASED_ON_PROMPT = (
    "Concisely name the object based on the following prompt. Use no more than 9 words."
)
NAME_PROJECT_BASED_ON_IMAGE = (
    "Concisely name the object based on the image given. Use no more than 9 words."
)

KLING_VIDEO_MV_PROMPT="Pan diagonally (horizontally and vertically) around this object showing different perspectives with this object in the center until it shows the back of this object. This object is static and doesn't move or animate at all. Draw the background as a unique color not present in this image."
KLING_VIDEO_MV_NEGATIVE_PROMPT="do not animate or move the object at all"