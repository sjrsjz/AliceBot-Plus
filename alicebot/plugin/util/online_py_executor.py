import aiohttp
async def execute_python_code(code):
    try:
        # online python executor
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://emkc.org/api/v1/piston/execute",
                json={"language": "python", "source": code},
            ) as response:
                response = await response.json()
                return response
    except Exception as e:
        return str(e)

