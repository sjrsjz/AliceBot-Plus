import asyncio
import websockets
import json
import base64

from typing import Callable, Any

log_func: Callable[[Any], None]


async def wolfram_alpha_compute(query, image_only=False):
    q = [{"t": 0, "v": query}]
    results = []
    async with websockets.connect('wss://gateway.wolframalpha.com/gateway') as websocket:
        msg = {"category": "results",
               "type": "init",
               "lang": "en",
               "wa_pro_s": "",
               "wa_pro_t": "",
               "wa_pro_u": "",
               "exp": 1714399254570,
               "displayDebuggingInfo": False,
               "messages": []}
        await websocket.send(json.dumps(msg))
        response = json.loads(await websocket.recv())
        if "type" in response and response["type"] != "ready":
            log_func("[Wolfram Alpha]Error:", response)
            return None
        log_func("[Wolfram Alpha]Response:", response)
        msg = {"type": "newQuery",
               "locationId": "oi8ft_en_light",
               "language": "en",
               "displayDebuggingInfo": False,
               "yellowIsError": False,
               "requestSidebarAd": False,
               "category": "results",
               "input": base64.b64encode(json.dumps(q).encode()).decode(),
               "i2d": True,
               "assumption": [],
               "apiParams": {},
               "file": None,
               "theme": "light"}
        log_func("[Wolfram Alpha]Sending Query:", msg)
        await websocket.send(json.dumps(msg))
        while True:
            response = await websocket.recv()
            json_ = json.loads(response)
            if "type" in json_ and json_["type"] == "queryComplete":
                break
            if "pods" not in json_:
                if "relatedQueries" in json_:
                    results.append([{"relatedQueries": json_["relatedQueries"]}])
                continue
            for pods in json_["pods"]:
                if "subpods" not in pods:
                    continue
                data = {}
                data.update({"title": pods["title"]})
                for subpods in pods["subpods"]:
                    if not image_only:
                        data.update({"plaintext": subpods["plaintext"]})
                    if "minput" in subpods and not image_only:
                        data.update({"minput": subpods["minput"]})
                    if "moutput" in subpods and not image_only:
                        data.update({"moutput": subpods["moutput"]})
                    if "img" in subpods and "data" in subpods["img"]:
                        data.update({"img_base64": subpods["img"]["data"]})
                    if "img" in subpods and "contenttype" in subpods["img"]:
                        data.update({"img_contenttype": subpods["img"]["contenttype"]})
                results.append(data)
    log_func("[Wolfram Alpha]Results:", results)
    return results


async def wolfram_alpha_compute_without_image(query):
    q = [{"t": 0, "v": query}]
    results = []
    async with websockets.connect('wss://gateway.wolframalpha.com/gateway') as websocket:
        msg = {"category": "results",
               "type": "init",
               "lang": "en",
               "wa_pro_s": "",
               "wa_pro_t": "",
               "wa_pro_u": "",
               "exp": 1714399254570,
               "displayDebuggingInfo": False,
               "messages": []}
        await websocket.send(json.dumps(msg))
        response = json.loads(await websocket.recv())
        if "type" in response and response["type"] != "ready":
            log_func("[Wolfram Alpha]Error:", response)
            return None
        log_func("[Wolfram Alpha]Response:", response)
        msg = {"type": "newQuery",
               "locationId": "oi8ft_en_light",
               "language": "en",
               "displayDebuggingInfo": False,
               "yellowIsError": False,
               "requestSidebarAd": False,
               "category": "results",
               "input": base64.b64encode(json.dumps(q).encode()).decode(),
               "i2d": True,
               "assumption": [],
               "apiParams": {},
               "file": None,
               "theme": "light"}
        log_func("[Wolfram Alpha]Sending Query:", msg)
        await websocket.send(json.dumps(msg))
        while True:
            response = await websocket.recv()
            json_ = json.loads(response)
            if "type" in json_ and json_["type"] == "queryComplete":
                break
            if "pods" not in json_:
                if "relatedQueries" in json_:
                    results.append([{"relatedQueries": json_["relatedQueries"]}])
                continue
            for pods in json_["pods"]:
                if "subpods" not in pods:
                    continue
                data = {}
                data.update({"title": pods["title"]})
                for subpods in pods["subpods"]:
                    data.update({"plaintext": subpods["plaintext"]})
                    if "minput" in subpods:
                        data.update({"minput": subpods["minput"]})
                    if "moutput" in subpods:
                        data.update({"moutput": subpods["moutput"]})
                results.append(data)
    log_func("[Wolfram Alpha]Results:", results)
    return results


async def format_to_mirai_ws(results):
    list_ = []
    n = len(results)
    i = 0
    for result in results:
        i += 1
        if "title" in result:
            list_ += [{"type": "Plain", "text": result["title"] + "\n"}]
        if "plaintext" in result:
            list_ += [{"type": "Plain", "text": "Expr:" + result["plaintext"] + "\n"}]
        if "img_base64" in result:
            list_ += [{"type": "Image", "base64": result['img_base64']}]
        if "minput" in result:
            list_ += [{"type": "Plain", "text": "Mathematica Input:" + result["minput"] + "\n"}]
        if "moutput" in result:
            list_ += [{"type": "Plain", "text": "Mathematica Output:" + result["moutput"] + "\n"}]
        if "relatedQueries" in result:
            list_ += [{"type": "Plain", "text": "Related Queries:\n"}]
            for query in result["relatedQueries"]:
                list_ += [{"type": "Plain", "text": query + "\n"}]
        if i < n:
            list_ += [{"type": "Plain", "text": "----------------------\n"}]
    if len(list_) == 0:
        return None
    if len(list_) > 0:
        if list_[-1]["type"] == "Plain":
            while len(list_) > 0 and list_[-1]["text"][-1] == "\n":
                list_[-1]["text"] = list_[-1]["text"][:-1]
    return list_


async def format_to_CQ(results):
    ret = ""
    for result in results:
        if "title" in result:
            ret += result["title"] + "\n"
        if "plaintext" in result:
            ret += "Expr:" + result["plaintext"] + "\n"
        if "img_base64" in result:
            ret += "[CQ:image,file=base64://" + result['img_base64'] + "]"
        if "minput" in result:
            ret += "Mathematica Input:" + result["minput"] + "\n"
        if "moutput" in result:
            ret += "Mathematica Output:" + result["moutput"] + "\n"
        if "relatedQueries" in result:
            ret += "Related Queries:\n"
            for query in result["relatedQueries"]:
                ret += query + "\n"

        ret += "----------------------\n"
    if len(ret) == 0:
        return None
    return ret


async def format_to_Markdown(results):
    ret = ""
    for result in results:
        if "title" in result:
            ret += result["title"] + "\n"
        if "plaintext" in result:
            ret += "Expr:" + result["plaintext"] + "\n"
        if "img_base64" in result:
            if "img_contenttype" in result:
                ret += f"![Image](data:{result['img_contenttype']};base64,{result['img_base64']})\n"
            else:
                ret += f"![Image](data:image/png;base64,{result['img_base64']})\n"
        if "minput" in result:
            ret += "Mathematica Input:" + result["minput"] + "\n"
        if "moutput" in result:
            ret += "Mathematica Output:" + result["moutput"] + "\n"
        if "relatedQueries" in result:
            ret += "Related Queries:\n"
            for query in result["relatedQueries"]:
                ret += query + "\n"

        # ret+="\n---\n"
    if len(ret) == 0:
        # 特殊情况, 用HTML的方式返回一个警告
        return """<div class=\"alert alert-warning\" role=\"alert\">No results</div>"""
    return ret


async def format_to_HTML(results):
    ret = '<div style="border: 1px solid #ccc; padding: 10px; margin: 10px; border-radius: 5px;">\n'
    for result in results:
        if "title" in result:
            ret += f"<h2>{result['title']}</h2>\n"
        if "plaintext" in result:
            ret += f"<p><strong>Expr:</strong> {result['plaintext']}</p>\n"
        if "img_base64" in result:
            if "img_contenttype" in result:
                ret += f"<p><img src='data:{result['img_contenttype']};base64,{result['img_base64']}' alt='Image' /></p>\n"
            else:
                ret += f"<p><img src='data:image/png;base64,{result['img_base64']}' alt='Image' /></p>\n"
        if "minput" in result:
            ret += f"<p><strong>Mathematica Input:</strong> {result['minput']}</p>\n"
        if "moutput" in result:
            ret += f"<p><strong>Mathematica Output:</strong> {result['moutput']}</p>\n"
        if "relatedQueries" in result:
            ret += "<p><strong>Related Queries:</strong></p>\n<ul>\n"
            for query in result["relatedQueries"]:
                ret += f"<li>{query}</li>\n"
            ret += "</ul>\n"

        ret += "<hr />\n"

    ret += '</div>\n'

    if len(ret) == 0:
        # 特殊情况, 用HTML的方式返回一个警告
        return """<div class="alert alert-warning" role="alert">No results</div>"""

    return ret


async def format_to_XML(results):
    ret = '<results>\n'
    for result in results:
        if "title" in result:
            ret += f"<title>{result['title']}</title>\n"
        if "plaintext" in result:
            ret += f"<plaintext>{result['plaintext']}</plaintext>\n"
        if "img_base64" in result:
            if "img_contenttype" in result:
                ret += f"<img contenttype='{result['img_contenttype']}'>{result['img_base64']}</img>\n"
            else:
                ret += f"<img contenttype='image/png'>{result['img_base64']}</img>\n"
        if "minput" in result:
            ret += f"<minput>{result['minput']}</minput>\n"
        if "moutput" in result:
            ret += f"<moutput>{result['moutput']}</moutput>\n"
        if "relatedQueries" in result:
            ret += "<relatedQueries>\n"
            for query in result["relatedQueries"]:
                ret += f"<query>{query}</query>\n"
            ret += "</relatedQueries>\n"

        ret += "<hr />\n"

    ret += '</results>\n'
    if len(ret) == 0:
        # 特殊情况, 用HTML的方式返回一个警告
        return """<alert>No results</alert>"""

    return ret


if __name__ == "__main__":
    asyncio.run(wolfram_alpha_compute("Python"))
