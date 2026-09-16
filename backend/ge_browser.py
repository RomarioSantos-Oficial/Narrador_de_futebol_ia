"""Read the ordinary public GE page with Edge, without private API requests.

No imported cookies, login, header spoofing, challenge solving or stealth modes.
If the public page refuses access, stop this source.
"""


class GEAccessUnavailable(Exception):
    pass


class GEPublicPage:
    def __init__(self, scripts=False):
        self.scripts = scripts

    async def __aenter__(self):
        from playwright.async_api import async_playwright
        self.driver = await async_playwright().start()
        try:
            self.browser = await self.driver.chromium.launch(channel="msedge", headless=True, args=["--disable-gpu"])
            self.context = await self.browser.new_context(java_script_enabled=self.scripts)
            self.page = await self.context.new_page()
            return self
        except BaseException:
            await self.driver.stop()
            raise

    async def __aexit__(self, *args):
        try:
            await self.browser.close()
        finally:
            await self.driver.stop()

    async def load(self, url):
        response = await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if response is None or response.status in (401, 403, 404, 429):
            code = response.status if response else "sem resposta"
            raise GEAccessUnavailable(f"A página GE está indisponível ({code}).")
        if response.status >= 400:
            raise RuntimeError(f"Falha temporária na página GE ({response.status}).")
        html = await self.page.content()
        if len(html) > 4 * 1024 * 1024:
            raise ValueError("Página GE excedeu o limite de leitura.")
        return html

