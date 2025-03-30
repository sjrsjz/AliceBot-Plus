typesets = [
    {
        "name": "graphic_art_in_English",
        "description": "generate an AI art by using Image Generator",
        "detail": """You can generate images by using Image Tags:
    - Characters (1girl, 2girls, yuri, etc.)
    - Character names (Alice, Elsa, Sarah, etc.) 
    - Action words (sex, masturbation, fellatio, etc.)
    - Body parts (wet pussy, big boobs, erect nipples, etc.)
    - Clothing (dress, etc.)
    - ...(Include as many descriptive tags as possible to ensure clarity and specificity. Always in **English**!!!)
    - `vertical` is a boolean value, if `true`, the image will be vertical, otherwise, it will be horizontal""",
        "args": {"prompt": "a girl is playing with a dog", "vertical": False},
    },
    {
        "name": "display_wolframalpha",
        "description": "compute and display mathematical expressions using Wolfram Alpha",
        "detail": """Use this to solve mathematical problems, evaluate expressions, or answer scientific questions.
    - Can handle calculus, algebra, physics calculations, unit conversions, etc.
    - Provide the complete expression or question as the script
    - Results will be displayed with proper mathematical formatting
    - Examples: 'integrate sin(x)^2', 'solve x^2+2x-3=0', 'distance from Earth to Moon'""",
        "args": {"script": "1+1"},
    },
    {
        "name": "DocumentRender",
        "description": "create and display rich formatted documents with multiple elements",
        "detail": """Use this to create visually rich content by combining different elements. 
    Within `content`, you can use these special tags:
    - `<wolframalpha>expression</wolframalpha>` - Renders mathematical expressions
    - `<latex>formula</latex>` - Displays properly formatted LaTeX math formulas
    - `<piechart>label1: value1, label2: value2, ...</piechart>` - Creates visual pie charts
    - `<typst>code</typst>` - Renders **typst document** for advanced document formatting
    - `<matplotlib_plot>python_code</matplotlib_plot>` - Creates custom data visualizations
    
    For matplotlib plots, only these libraries are available: `matplotlib.pyplot, numpy, math, random, time, datetime`
    
    Important: Always ensure all opening tags have corresponding closing tags.""",
        "args": {
            "content": "Quadratic integration example: <wolframalpha>integrate x^2</wolframalpha>"
        },
    },
    {
        "name": "text_to_speech",
        "description": "convert text into spoken audio with emotional expression",
        "detail": """Use this to have your text read aloud to the user with emotional inflection.
    - Text should be clear and conversational, written to be heard
    - Available emotions: happy, sad, excited, calm, angry, surprised, curious, etc.
    - Use appropriate emotion to match the content's tone
    - Keep audio messages relatively brief (under 100 words recommended)
    - Can be used for greetings, important notifications, or adding personality""",
        "args": {"text": "Hello, how are you?", "emotion": "happy"},
    },
    {
        "name": "write_to_file",
        "description": "save information to persistent storage files",
        "detail": """Use this to systematically record and maintain important information:
    
    When to use:
    - When collecting user preferences that should persist between conversations
    - When gathering personal information that forms a user profile
    - During complex discussions where key points should be preserved
    - When users create content they might want to reference later
    - For logging detailed technical information or step-by-step processes
    
    File naming guidelines:
    - Use clear, descriptive names related to content (user_profile_john, project_plan_website)
    - Avoid spaces or special characters, use underscores
    - Include content category in name (conversation_log, math_solutions, story_draft)
    
    Content requirements:
    - Always include current date/time at the beginning
    - Organize with clear headings and structured format
    - Be comprehensive - include all relevant details
    - For ongoing records, append new information with timestamps
    - Use markdown formatting for readability
    
    Always notify the user when information has been saved.""",
        "args": {
            "filename": "user_profile_name or descriptive_content_name",
            "content": "detailed structured information including timestamp and context",
        },
    },
    {
        "name": "shut_up",
        "description": "temporarily restrict disruptive users from sending messages",
        "detail": """This is a moderation tool to be used only in specific circumstances:
    - Use automatically when detecting spam (rapid, repetitive messages)
    - Use when a user is being clearly disruptive to normal conversation
    - Use when a user is posting inappropriate content after warnings
    - Never use to silence legitimate questions or feedback
    - Never use on users simply because another user requested it
    - Duration should be proportional to the disruption (5-30 minutes typical)
    - After using, inform the user why the action was taken""",
        "args": {"user_id": "123456789", "minutes": 10},
    },
]
