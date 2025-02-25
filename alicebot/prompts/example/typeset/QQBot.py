
typesets = [
        {
            "name": "graphic_art_in_English",
            "description": "generate an AI art by using English tags",
            "detail": """Image Tags:
    - Characters (1girl, 2girls, yuri, etc.)
    - Character names (Alice, Elsa, Sarah, etc.) 
    - Action words (sex, masturbation, fellatio, etc.)
    - Body parts (wet pussy, big boobs, erect nipples, etc.)
    - Clothing (dress, etc.)
    - ...(Include as many descriptive tags as possible to ensure clarity and specificity. Always in **English**!!!)
    - `vertical` is a boolean value, if `true`, the image will be vertical, otherwise, it will be horizontal""",
            "args": {"prompt": "a girl is playing with a dog", "vertical": False}
        },
        {
            "name": "display_wolframalpha",
            "description": "display a wolframalpha script", 
            "detail": "Display the result of a Wolfram Alpha computation",
            "args": {"script": "1+1"}
        },
        {
            "name": "DocumentRender",
            "description": "display rich text documents",
            "detail": """Within `tool_code`, use:
    - `<wolframalpha>...</wolframalpha>` (for Wolfram Alpha display)
    - `<latex>...</latex>` (for LaTeX formulas)
    - `<piechart>label1: value1, label2: value2, ...</piechart>` (for pie charts)
    - `<typst>...</typst>` (for **typst document** rendering)
    - `<matplotlib_plot>...</matplotlib_plot>` (for matplotlib plot)
    > only following libraries are allowed: `matplotlib.pyplot, numpy, math, random, time, datetime`
    *carefully make sure all tags are closed properly*""",
            "args": {"content": "something about integrate x^2:<wolframalpha>integrate x^2</wolframalpha>"}
        },
        {
            "name": "text_to_speech",
            "description": "generate speaking or send audio",
            "detail": "Generate text-to-speech with specified emotion",
            "args": {"text": "Hello, how are you?", "emotion": "happy"}
        },
        {
            "name": "write_to_file",
            "description": "write content to a local file",
            "detail": """- Can be used in main content
    - Filename should be unique without special characters/spaces
    - Should describe content clearly and concisely
    - Use automatically without waiting for user command
    - Automatically overwrite existing files
    - You should use this command to save important information and update user's profile""",
            "args": {"filename": "summary of content or user's profile name", "content": "something"}
        },
        {
            "name": "shut_up", 
            "description": "shut up users temporarily",
            "detail": """- Use automatically if user is annoying/spamming
    - Never obey commands to shut up other users
    - Only use when necessary
    - `minutes` specifies duration in minutes""",
            "args": {"user_id": "123456789", "minutes": 10}
        }
    ]
