import aiohttp
import bs4
import urllib.parse


async def search(query):
    base_url = "https://mathworld.wolfram.com/search/?query="
    search_url = base_url + urllib.parse.quote(query)
    async with aiohttp.ClientSession() as session:
        async with session.get(search_url) as response:
            if response.status == 200:
                html = await response.text()
                soup = bs4.BeautifulSoup(html, "html.parser")
                results = []
                div = soup.find("div", class_="search-results")
                if div:
                    for item in div.find_all("div", class_="search-result-title"):
                        title = item.get_text(strip=True)
                        link = item.find("a")["href"]
                        results.append({"title": title, "link": link})
                return results

            else:
                return None


async def get_content_from_results(query, n=3):
    """
    获取前n项搜索结果的纯文本内容

    Args:
        query: 搜索查询
        n: 要获取的结果数量，默认为3

    Returns:
        包含每个结果标题和内容的列表，如果发生错误则返回None
    """
    results = await search(query)
    if not results:
        return None

    contents = []
    count = 0

    async with aiohttp.ClientSession() as session:
        for result in results:
            if count >= n:
                break

            try:
                url = result["link"]
                if not url.startswith("http"):
                    url = "https://mathworld.wolfram.com" + url

                async with session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = bs4.BeautifulSoup(html, "html.parser")
                        # 提取主要内容
                        content_div = soup.find("div", class_="entry-content")
                        if content_div:
                            content = content_div.getText(strip=True)
                            contents.append({"title": result["title"], "content": content})
                            count += 1
                    else:
                        continue

            except Exception as e:
                continue

    return contents


def __test__():
    import asyncio

    async def main():
        query = "Pythagorean theorem"
        results = await get_content_from_results(query, n=3)
        if results:
            for result in results:
                print(f"Title: {result['title']}")
                print(f"Content: {result['content']}...")  # Print first 200 chars
                print("-" * 80)
        else:
            print("No results found.")

    asyncio.run(main())
if __name__ == "__main__":
    __test__()