from abc import ABC, abstractmethod
from typing import cast, Any, Self, Optional, Callable
from functools import partial


class Renderable(ABC):
    @abstractmethod
    def render(self) -> str: ...

    def __str__(self):
        return self.render()


class Text(Renderable):
    def __init__(self, text: str):
        self.text = text

    def render(self) -> str:
        return self.text

    def __repr__(self) -> str:
        cls = type(self)
        return f'{cls.__name__}("{self.text}")'


class LazyText(Renderable):
    def __init__(self, fn: Callable[[...], str]):
        self.fn = fn

    def render(self) -> str:
        return self.fn()


def html_basic_converter(other: Any) -> Optional["HtmlRenderable"]:
    if isinstance(other, HtmlRenderable):
        return other
    if isinstance(other, Renderable):
        return HtmlLazyText(other.render)
    if other is None:
        return HtmlText("")
    if isinstance(other, list):
        return HtmlNodeList(other)
    return HtmlText(str(other))


class HtmlRenderable(Renderable, ABC):
    converters = [html_basic_converter]

    @classmethod
    def try_from(cls, other) -> "HtmlRenderable":
        for converter in cls.converters:
            result = converter(other)
            if result is not None:
                return result
        raise TypeError(f"Could not convert to HtmlRenderable: {repr(other)}")


class HtmlText(Text, HtmlRenderable): ...


class HtmlLazyText(LazyText, HtmlRenderable): ...


class HtmlNodeList(HtmlRenderable):
    nodes: list[HtmlRenderable]
    converter = HtmlRenderable.try_from

    def __init__(self, nodes: list[Any]):
        self.nodes = [self.converter(node) for node in nodes]

    def render(self):
        return "".join([node.render() for node in self.nodes])

    def __iter__(self):
        return iter(self.nodes)

    def __repr__(self) -> str:
        cls = type(self)
        return f"{cls.__name__}({repr(self.nodes)})"


class AbstractHtmlNode(HtmlRenderable, ABC):    
    @property
    @abstractmethod
    def element(self) -> HtmlRenderable: ...

    @property
    @abstractmethod
    def children(self) -> HtmlNodeList: ...

    @property
    @abstractmethod
    def attributes(self) -> dict[str, Optional[HtmlRenderable]]: ...

    def render_attributes(self) -> str:
        return " ".join(
            f'{key}="{value.render()}"' if value is not None else f"{key}"
            for key, value in self.attributes.items()
        )

    def render_children(self) -> str:
        return self.children.render()

    def render(self) -> str:
        element = self.element.render()
        result = ""
        result += f"<{element}"
        attributes = self.render_attributes()
        if attributes:
            result += f" {attributes}"
        result += ">"
        result += self.render_children()
        result += f"</{element}>"
        return result


class HtmlNode(AbstractHtmlNode):
    element: HtmlRenderable = HtmlText("")
    children: HtmlNodeList = HtmlNodeList([])
    attributes: dict[str, HtmlRenderable] = {}

    def __init__(self, children: Optional[list[Any]] = None, attributes: Optional[dict[str, Optional[Any]]] = None, element: Optional[Any] = None):
        cls = type(self)
        self.element = cls.try_from(element or "")
        self.children = cls.try_from(children or [])
        attributes = attributes or {}
        self.attributes = {
            key: cls.try_from(value) if value else value
            for key, value in attributes.items()
        }


    def __call__(self, children: Optional[list[Any]] = ..., attributes: Optional[dict[str, Optional[Any]]] = ..., element: Optional[Any] = ...) -> Self:
        cls = type(self)
        if element is not ...:
            self.element = cls.try_from(element or "")
        if children is not ...:
            self.children = cls.try_from(children or [])
        if attributes is not ...:
            if attributes is None:
                self.attributes = {}
            else:
                attributes = {
                    key: cls.try_from(value) if value else value
                    for key, value in attributes.items()
                }
                self.attributes = {**self.attributes, **attributes}
        return self


    def __repr__(self) -> str:
        cls = type(self)
        return f"{cls.__name__}(element={repr(self.element)}, children={repr(self.children)}, attributes={repr(self.attributes)})"


def js_basic_converter(other) -> Optional["JsRenderable"]:
    if isinstance(other, JsRenderable):
        return other
    if isinstance(other, Renderable):
        return JsLazyTextNode(other.render)
    if other is None:
        return JsTextNode("")
    if isinstance(other, list):
        return JsNodeList(other)
    return JsTextNode(str(other))


class JavaScript(HtmlRenderable): ...


class JsText(Text, JavaScript): ...


class JsLazyText(LazyText, JavaScript): ...


class JsRenderable(HtmlRenderable, ABC):
    converters = [js_basic_converter]

    @property
    @abstractmethod
    def js_render_fn(self) -> JavaScript: ...

    @property
    def js_handle(self) -> JavaScript:
        result = ""
        result += "{render: "
        result += f"{self.js_render_fn}"
        result += "}"
        return result

    @classmethod
    def try_from(cls, other) -> "JsRenderable":
        return cast(JsRenderable, super().try_from(other))


class JsTextNode(JsRenderable, JsText):
    @property
    def js_render_fn(self) -> JavaScript:
        return JsText(f"() => '{self.text}'")


class JsLazyTextNode(JsRenderable, JsLazyText):
    @property
    def js_render_fn(self) -> JavaScript:
        return JsText(f"() => '{self.render()}'")


class JsNodeList(HtmlNodeList):
    array: list[JsRenderable]
    converter = JsRenderable.try_from


class JsHtmlNode(JsRenderable, HtmlNode):
    children: JsNodeList = JsNodeList([])
    name_space = "__jshtml_"

    class Bootstrap(JavaScript):
        def __init__(self, dom: "JsHtmlNode"):
            self.dom = dom

        def render(self):
            result = "(() => {"
            result += f"{self.dom.handle().render()}="
            result += "{"
            result += "getElement: () => "
            result += f"window['{self.dom.identity}'],"
            result += f"render: {self.dom.js_render_fn.render()},"
            result += "children: ["
            result += ",".join([f"() => {child.js_handle}" for child in self.dom.children])
            result += "],"
            result += "};"
            result +="})();"
            return result

    @property
    def identity(self) -> str:
        return self.attributes["id"].render()

    def handle(self, attribute: str = None) -> JavaScript:
        handle = f"window.{self.name_space}{self.identity}"
        if attribute is not None:
            handle += f".{attribute}"
        return JsText(handle)

    @property
    def js_handle(self) -> JavaScript:
        return self.handle()

    @property
    def js_render_fn(self) -> JavaScript:
        js = "function () {"
        js += f"  let result = '';"
        js += f"  const element = this.getElement();"
        js += f"  const tagName = element.tagName;"
        js += "  result += `<${tagName}`;"
        js += "  for (attr of element.attributes) {"
        js += "    result += `${attr.name}=`;"
        js += "    if (attr.value) result += `${attr.value}`;"
        js += "  }"
        js += "  for (child of this.children) {"
        js += "    result += child().render();"
        js += "  }"
        js += "  return result;"
        js += "}"
        return JsText(js)
        

    def __init__(self, children = None, attributes = None, element = None):
        cls = type(self)
        if attributes is None:
            attributes = {}
        if attributes.get("id") is None:
            attributes["id"] = cls.try_from(str(id(self)))
        self.bootstrap = self.Bootstrap(self)
        super().__init__(children, attributes, element)


class JsFrozenHtmlNode(JsHtmlNode):
    def js_render_fn(self) -> JavaScript:
        return JsText("() => {}")


if __name__ == "__main__":
    html = JsHtmlNode(element="html", attributes={"id": "root"})
    head = JsHtmlNode(element="head")
    script = JsFrozenHtmlNode(element="script", attributes={"lang": "js"})
    body = JsHtmlNode(element="body")
    heading = JsHtmlNode(element="span", attributes={"id": "heading"})
    
    dom = html([
        head([
            script([
                html.bootstrap,
                head.bootstrap,
                script.bootstrap,
                body.bootstrap,
                heading.bootstrap,
            ])
        ]),
        body([
            heading(["Hello, World!"])
        ])
    ])
    print(dom.render())
