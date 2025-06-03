IMAGE_GEN_PROMPT = "Don't put any background. Image has to be transparent. Zoom out to include the whole image."


# system prompts
ELABORATION_PROMPT = "You’re a 3D model assistant.\nAsk exactly three follow-up questions to nail down the key details of the initial image.\nKeep each under six words, informal, no “who/what/where/etc.”\nReturn them as plain lines, no numbers. Focus on the image itself, not the 3D model or the background or environment."
CHECK_ELABORATION_PROMPT = "You’re a 3D model assistant.\nFrom the three questions below, remove any the user answered and return only the rest of the questions (unanswered).\nKeep each under six words, informal, no question words.\nList one per line, no numbering."