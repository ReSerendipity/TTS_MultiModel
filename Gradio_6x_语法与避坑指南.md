# Gradio 6.x 完整语法与避坑指南

> 适用版本：Gradio 6.x（推荐 6.14.x）| 最低 Python ≥ 3.10

---

## 目录

- [一、gr.Interface 语法](#一grinterface-语法)
- [二、gr.ChatInterface 语法](#二grchatinterface-语法)
- [三、gr.Blocks 语法](#三grblocks-语法)
- [四、布局语法](#四布局语法)
- [五、所有组件语法](#五所有组件语法)
- [六、事件绑定语法](#六事件绑定语法)
- [七、then / catch 链式调用](#七then--catch-链式调用)
- [八、gr.render 动态渲染](#八grrender-动态渲染)
- [九、gr.State 状态管理](#九grstate-状态管理)
- [十、gr.Examples 示例组件](#十grexamples-示例组件)
- [十一、流式输出 Streaming](#十一流式输出-streaming)
- [十二、gr.Progress 进度条](#十二grprogress-进度条)
- [十三、主题语法](#十三主题语法)
- [十四、api() 调用远程应用](#十四api-调用远程应用)
- [十五、静默失败陷阱大全（必读）](#十五静默失败陷阱大全必读)
- [十六、快速排查清单](#十六快速排查清单)

---

## 一、`gr.Interface` 语法

```python
import gradio as gr

demo = gr.Interface(
    fn=处理函数,                    # 必填：你的处理函数
    inputs=组件或组件列表,           # 必填：输入组件
    outputs=组件或组件列表,          # 必填：输出组件
    title="应用标题",               # 可选
    description="应用描述",          # 可选
    examples=[["示例1"], ["示例2"]], # 可选：示例数据
    cache_examples=True,            # 可选：缓存示例（布尔值）
    cache_mode="eager",             # 可选："eager" 或 "lazy"
    api_name="predict",             # 可选：API 端点名称
)
demo.launch()
```

### inputs/outputs 的简写形式

```python
inputs="text"          # 等同于 gr.Textbox()
inputs="image"         # 等同于 gr.Image()
inputs="audio"         # 等同于 gr.Audio()
inputs="video"         # 等同于 gr.Video()
inputs="file"          # 等同于 gr.File()
inputs="number"        # 等同于 gr.Number()
inputs="slider"        # 等同于 gr.Slider()
inputs="checkbox"      # 等同于 gr.Checkbox()
inputs="radio"         # 等同于 gr.Radio()
inputs="dropdown"      # 等同于 gr.Dropdown()
inputs="textbox"       # 等同于 gr.Textbox()
inputs="markdown"      # 等同于 gr.Markdown()
inputs="json"          # 等同于 gr.JSON()
inputs="dataframe"     # 等同于 gr.Dataframe()
inputs="gallery"       # 等同于 gr.Gallery()
```

---

## 二、`gr.ChatInterface` 语法

```python
demo = gr.ChatInterface(
    fn=聊天函数,                    # 必填
    # fn 的签名必须是：(message: str, history: list) -> str
    type="messages",                # 6.x 默认值，只能用 "messages"
    chatbot=gr.Chatbot(height=400), # 可选：自定义 Chatbot 组件
    textbox=gr.Textbox(placeholder="输入消息..."),  # 可选
    title="标题",
    description="描述",
    examples=[                     # 示例格式（6.x 新格式）
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "嗨！有什么可以帮你的？"}
    ],
    example_labels=["打招呼"],      # 示例标签
    cache_examples=False,
    retry_btn="重试",
    undo_btn="撤销",
    clear_btn="清空",
    submit_btn="发送",
    autofocus=True,
)
```

### 聊天函数的标准写法

```python
def chat(message, history):
    """
    message: str — 用户当前输入
    history: list[dict] — 历史消息列表
             [{"role": "user", "content": "..."},
              {"role": "assistant", "content": "..."}]
    返回: str — 助手回复内容
    """
    return f"你说了：{message}"
```

---

## 三、`gr.Blocks` 语法

```python
with gr.Blocks(
    # ⚠️ 6.x 变更：以下参数已移到 launch()
    # theme, css, js, head, css_paths, head_paths 不再放在这里
) as demo:
    # 组件定义
    # 布局定义
    # 事件绑定
    pass

demo.launch(
    theme=gr.themes.Soft(),         # 主题
    css="自定义CSS",                # 自定义样式
    js="自定义JS",                  # 自定义脚本
    head="自定义HTML head",         # 自定义 head 内容
    css_paths=["style.css"],        # CSS 文件路径
    head_paths=["custom.html"],     # HTML 文件路径
    server_name="0.0.0.0",         # 服务器地址
    server_port=7860,              # 端口
    share=False,                   # 是否生成公开链接
    footer_links=["api", "gradio", "settings"],  # 6.x 新参数
    # ⚠️ 6.x 变更：show_api 已移除，用 footer_links 替代
)
```

---

## 四、布局语法

```python
with gr.Blocks() as demo:
    # ===== 垂直排列（默认）=====
    gr.Textbox(label="A")
    gr.Textbox(label="B")       # B 在 A 下方

    # ===== 水平排列 =====
    with gr.Row():
        gr.Textbox(label="左")
        gr.Textbox(label="右")

    # ===== 等宽水平排列 =====
    with gr.Row(equal_height=True):
        gr.Textbox(label="A")
        gr.Image(label="B")

    # ===== 多列布局 =====
    with gr.Row():
        with gr.Column(scale=1):      # 占 1 份宽度
            gr.Textbox(label="窄")
        with gr.Column(scale=3):      # 占 3 份宽度
            gr.Textbox(label="宽")

    # ===== 标签页 =====
    with gr.Tabs():
        with gr.Tab("标签1"):
            gr.Textbox(label="内容1")
        with gr.Tab("标签2"):
            gr.Image(label="内容2")

    # ===== 手风琴折叠 =====
    with gr.Accordion("点击展开", open=False):
        gr.Textbox(label="隐藏内容")

    # ===== 分组 =====
    with gr.Group():
        gr.Textbox(label="A")
        gr.Textbox(label="B")

    # ===== 条件渲染 =====
    with gr.Row(visible=False) as hidden_row:
        gr.Textbox(label="默认隐藏")
    # 通过事件修改：hidden_row.visible = True
```

---

## 五、所有组件语法

### 文本类

```python
gr.Textbox(
    label="标签",
    placeholder="占位文字",
    value="默认值",
    lines=1,                    # 行数，>1 变为文本域
    max_lines=20,               # 最大行数
    type="text",                # "text" | "password" | "email"
    show_copy_button=True,      # 显示复制按钮
    autofocus=False,            # 自动聚焦
    interactive=True,           # 是否可交互
    visible=True,               # 是否可见
    elem_id="my-textbox",       # HTML id
    elem_classes=["my-class"],  # HTML class
)

gr.Number(
    label="标签",
    value=0,                    # 默认值
    minimum=None,               # 最小值
    maximum=None,               # 最大值
    step=None,                  # 步长
    precision=None,             # 精度（小数位数）
)

gr.Markdown(
    value="## 标题\n**粗体** *斜体*",
    elem_id="my-md",
)

gr.JSON(
    value={"key": "value"},
    label="标签",
)
```

### 选择类

```python
gr.Dropdown(
    choices=["选项A", "选项B", "选项C"],
    value="选项A",              # 默认选中
    label="标签",
    multiselect=False,          # 是否多选
    allow_custom_value=False,   # 是否允许自定义输入
    filterable=True,            # 是否可搜索过滤
)

gr.Radio(
    choices=["选项A", "选项B"],
    value="选项A",
    label="标签",
    type="value",               # "value" | "index"
)

gr.Checkbox(
    label="同意条款",
    value=False,
)

gr.CheckboxGroup(
    choices=["Python", "JS", "Go"],
    value=["Python"],
    label="标签",
)

gr.Slider(
    minimum=0,
    maximum=100,
    value=50,
    step=1,
    label="标签",
    interactive=True,
)
```

### 媒体类

```python
gr.Image(
    type="filepath",            # "filepath" | "numpy" | "pil"
    label="标签",
    sources=["upload", "clipboard", "webcam"],  # 图片来源
    image_mode="RGB",           # "RGB" | "RGBA" | "L"
    shape=None,                 # (height, width)
    height=None,                # 显示高度
    width=None,                 # 显示宽度
    interactive=True,
    show_download_button=True,
    show_share_button=False,
    elem_id="my-img",
)

gr.Audio(
    type="filepath",            # "filepath" | "numpy"
    sources=["upload", "microphone"],
    label="标签",
    waveform_options=None,
)

gr.Video(
    label="标签",
    sources=["upload", "webcam"],
)

gr.File(
    label="标签",
    file_count="single",        # "single" | "multiple"
    file_types=None,            # [".pdf", ".txt"] 限制文件类型
    type="filepath",
)

gr.Gallery(
    label="标签",
    columns=2,                  # 列数
    rows=2,                     # 行数
    height="auto",
    object_fit="contain",       # "contain" | "cover" | "fill"
)
```

### 数据展示类

```python
gr.Dataframe(
    value=[[1, "A"], [2, "B"]],
    headers=["ID", "名称"],
    label="标签",
    datatype=["number", "str"], # 列类型
    row_count=5,                # 初始行数
    row_limits=(1, 100),        # 行数限制 (min, max)
    column_count=2,             # 初始列数
    column_limits=None,         # 列数限制
    interactive=True,
    max_height=500,
)

gr.Label(
    value={"猫": 0.9, "狗": 0.1},
    num_top_classes=3,
)

gr.Plot(label="图表")

gr.HTML(
    value="<div>自定义HTML</div>",
    padding=False,              # 6.x 默认 False
)

gr.Chatbot(
    value=[
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "嗨！"}
    ],
    type="messages",            # 6.x 只支持 "messages"
    height=400,
    like_user_message=False,    # 6.x 放在构造函数里
    avatar_images=(user_path, bot_path),
    show_copy_button=True,
)
```

---

## 六、事件绑定语法

### 基础事件

```python
组件.事件名(
    fn=函数,                    # 处理函数
    inputs=输入组件列表,         # 列表
    outputs=输出组件列表,        # 列表
    api_name="端点名",           # API 端点名称
    api_visibility="public",     # 6.x 新参数
    show_progress="full",       # "full" | "minimal" | "hidden"
    queue=True,                 # 是否排队
    concurrency_limit=None,     # 并发限制
    scroll_to_output=False,     # 自动滚动到输出
    trigger_mode="once",        # "once" | "multiple" | "always_last"
)
```

### 可用事件名

```python
btn.click(...)                 # 点击按钮
textbox.submit(...)            # 按回车提交
textbox.change(...)            # 内容变化
textbox.input(...)             # 每次输入（实时）
textbox.focus(...)             # 获得焦点
textbox.blur(...)              # 失去焦点
dropdown.change(...)           # 选择变化
slider.change(...)             # 滑块变化
slider.release(...)            # 松开滑块
image.upload(...)              # 上传图片
image.change(...)              # 图片变化
file.upload(...)               # 上传文件
number.change(...)             # 数值变化
checkbox.change(...)           # 勾选变化
radio.change(...)              # 单选变化
tab.select(...)                # 切换标签页
demo.load(...)                 # 页面加载时
```

### 错误处理

```python
# 方式一：链式 catch
组件.事件名(...).then(...).catch(fn=error_handler)

# 方式二：failure 事件
组件.事件名(...).failure(fn=error_handler)
```

---

## 七、`then` / `catch` 链式调用

```python
btn.click(fn=step1, inputs=[a], outputs=[b]) \
  .then(fn=step2, inputs=[b], outputs=[c]) \
  .then(fn=step3, inputs=[c], outputs=[d])

# 带错误处理
btn.click(fn=risky_operation, outputs=[result]) \
  .then(fn=success_handler) \
  .catch(fn=error_handler)
```

---

## 八、`gr.render` 动态渲染

```python
import gradio as gr

with gr.Blocks() as demo:
    num = gr.Number(label="输入数量", value=1)

    @gr.render(inputs=[num])
    def dynamic_fields(n):
        for i in range(int(n)):
            yield gr.Textbox(label=f"字段 {i+1}")

    btn = gr.Button("提交")
    btn.click(fn=collect_all, inputs=[num], outputs=[gr.Textbox()])

demo.launch()
```

---

## 九、`gr.State` 状态管理

```python
with gr.Blocks() as demo:
    counter = gr.State(value=0)     # 隐藏状态变量
    display = gr.Number(label="计数")

    def increment(count):
        return count + 1

    btn = gr.Button("+1")
    btn.click(fn=increment, inputs=[counter], outputs=[counter])

    # 监听 State 变化来更新显示
    counter.change(fn=lambda x: x, inputs=[counter], outputs=[display])
```

---

## 十、`gr.Examples` 示例组件

```python
gr.Examples(
    examples=[
        ["你好", "世界"],
        ["Gradio", "真棒"],
    ],
    inputs=[textbox1, textbox2],
    outputs=result,
    fn=process,
    cache_examples=True,
    cache_mode="eager",           # "eager" | "lazy"
    label="示例",
)
```

---

## 十一、流式输出 Streaming

```python
# ChatInterface 中的流式
def stream_response(message, history):
    partial = ""
    for word in message.split():
        partial += word + " "
        yield partial              # 用 yield 逐步返回

demo = gr.ChatInterface(fn=stream_response)
```

```python
# Blocks 中的流式
def stream(text):
    for i in range(len(text)):
        yield text[:i+1]

btn.click(fn=stream, inputs=[inp], outputs=[out])
```

---

## 十二、`gr.Progress` 进度条

```python
def long_task(text, progress=gr.Progress()):
    for i in progress.tqdm(range(100), desc="处理中"):
        import time
        time.sleep(0.05)
    return "完成！"

demo = gr.Interface(fn=long_task, inputs="text", outputs="text")
```

---

## 十三、主题语法

```python
demo.launch(
    theme=gr.themes.Default(),    # 默认主题
    # theme=gr.themes.Soft(),    # 柔和
    # theme=gr.themes.Glass(),   # 玻璃
    # theme=gr.themes.Monochrome(), # 单色
    # theme=gr.themes.Base(),    # 基础
)
```

### 自定义主题颜色

```python
theme = gr.themes.Soft(
    primary_hue="orange",         # 主色调
    secondary_hue="blue",         # 次要色调
    neutral_hue="gray",           # 中性色调
    font=gr.themes.GoogleFont("Noto Sans SC"),
)
demo.launch(theme=theme)
```

---

## 十四、`api()` 调用远程应用

```python
import gradio as gr

# 连接远程 Gradio 应用
client = gr.Client("spaces/username/space-name")

# 调用 API
result = client.predict("输入内容")
```

---

## 十五、静默失败陷阱大全（必读）

> Gradio 很多语法错误**不会报错**，只是静默忽略。这是 AI 改代码时最容易踩的坑。

### 陷阱 1：`launch()` vs `Blocks()` 参数放错位置（最高频）

6.x 把参数从 `Blocks()` 移到了 `launch()`，但放错位置**不报错**，只是静默忽略。

```python
# ❌ 静默失败 — 不报错，但主题和CSS不生效
with gr.Blocks(theme=gr.themes.Soft(), css=".my{color:red}") as demo:
    gr.Textbox(label="测试")
demo.launch()

# ✅ 正确 — 参数放在 launch() 里
with gr.Blocks() as demo:
    gr.Textbox(label="测试")
demo.launch(theme=gr.themes.Soft(), css=".my{color:red}")
```

**必须放在 `launch()` 的参数：** `theme`、`css`、`js`、`head`、`css_paths`、`head_paths`

---

### 陷阱 2：CSS 选择器写错

CSS 写错了**不报错**，只是样式不生效。

```python
# ❌ 静默失败 — 没有指定 elem_id，CSS 选择器找不到元素
with gr.Blocks() as demo:
    gr.Textbox(label="测试")          # 没有 elem_id！
demo.launch(css="#my-input { color: red; }")

# ✅ 正确 — 必须用 elem_id 匹配
with gr.Blocks() as demo:
    gr.Textbox(label="测试", elem_id="my-input")
demo.launch(css="#my-input { color: red; }")
```

**常见 CSS 选择器错误：**

```python
# ❌ 用 label 文字当选择器（无效）
css='#"用户名" { color: red; }'

# ❌ 用组件类型当选择器（无效）
css='textbox { color: red; }'

# ✅ 用 elem_id
css='#my-textbox { color: red; }'

# ✅ 用 elem_classes
css='.my-class { color: red; }'
```

**Gradio 组件的实际 HTML 结构（CSS 选择器需要匹配这个）：**

```html
<!-- gr.Textbox 生成的实际结构 -->
<div class="gradio-textbox" id="my-textbox">
    <label>标签</label>
    <input type="text" />
</div>

<!-- 所以 CSS 要这样写才有效 -->
# my-textbox input { border: 2px solid red; }     /* 选中输入框 */
# my-textbox label { color: blue; }                /* 选中标签 */
```

---

### 陷阱 3：事件绑定返回值数量不匹配

**不报错**，只是输出组件不更新。

```python
# ❌ 静默失败 — 函数返回2个值，但 outputs 只有1个
def process(text):
    return "结果1", "结果2"       # 返回了2个值

btn.click(fn=process, inputs=[inp], outputs=[out1])  # 只接收1个

# ✅ 正确 — 返回值数量必须和 outputs 数量一致
btn.click(fn=process, inputs=[inp], outputs=[out1, out2])
```

```python
# ❌ 静默失败 — 函数返回1个值，但 outputs 有2个
def process(text):
    return "结果"               # 只返回1个

btn.click(fn=process, inputs=[inp], outputs=[out1, out2])  # 期望2个

# ✅ 正确
def process(text):
    return "结果1", "结果2"
```

---

### 陷阱 4：`inputs` / `outputs` 类型错误

```python
# ❌ 静默失败 — inputs 传了字符串而不是组件对象
btn.click(fn=process, inputs="text", outputs=out)

# ✅ 正确 — 必须传组件对象
textbox = gr.Textbox()
btn.click(fn=process, inputs=[textbox], outputs=[out])
```

```python
# ❌ 静默失败 — outputs 传了字符串
btn.click(fn=process, inputs=[inp], outputs="text")

# ✅ 正确
out = gr.Textbox()
btn.click(fn=process, inputs=[inp], outputs=[out])
```

---

### 陷阱 5：`visible` 修改不生效

```python
# ❌ 静默失败 — 直接修改 visible 属性，不会触发 UI 更新
with gr.Blocks() as demo:
    row = gr.Row(visible=False)
    gr.Textbox(label="隐藏内容")

def show():
    row.visible = True    # 这不会让界面更新！
    return "已显示"

# ✅ 正确 — 通过 outputs 返回 gr.update() 来修改
with gr.Blocks() as demo:
    with gr.Column(visible=False) as col:
        txt = gr.Textbox(label="内容")

def show():
    return gr.update(visible=True)

btn.click(fn=show, outputs=[col])  # col 作为 output
```

---

### 陷阱 6：Chatbot 消息格式错误

不报错但显示空白。

```python
# ❌ 静默失败 — 6.x 不再支持 tuple 格式，但不报错，只是显示空白
chatbot = gr.Chatbot(value=[["你好", "嗨"]])

# ❌ 静默失败 — 缺少 type="messages"
chatbot = gr.Chatbot(value=[
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "嗨"}
])

# ✅ 正确
chatbot = gr.Chatbot(
    type="messages",
    value=[
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "嗨"}
    ]
)
```

---

### 陷阱 7：ChatInterface 函数签名错误

```python
# ❌ 静默失败 — 参数名或数量不对，不报错但功能异常
def chat(prompt):          # 缺少 history 参数
    return "回复"

# ❌ 静默失败 — 返回了 list 而不是 str
def chat(message, history):
    return [{"role": "assistant", "content": "回复"}]

# ✅ 正确 — 必须是 (message, history) 两个参数，返回 str
def chat(message, history):
    return "回复内容"
```

---

### 陷阱 8：`gr.update()` 用法错误

```python
# ❌ 静默失败 — 用错了属性名
gr.update(value="新值", label="新标签")  # label 不能通过 update 修改

# ✅ 可更新的属性（因组件而异）
gr.update(value="新值")           # 修改值
gr.update(visible=True/False)     # 修改可见性
gr.update(interactive=True/False) # 修改是否可交互
gr.update(choices=["A", "B"])     # 修改选项（Dropdown/Radio等）
gr.update(placeholder="提示")     # 修改占位符
gr.update(label="新标签")         # ⚠️ 部分组件支持，部分不支持
gr.update(maximum=200)            # 修改最大值（Slider/Number等）
```

---

### 陷阱 9：`then()` 链式调用中 inputs 引用错误

```python
# ❌ 静默失败 — then 中引用了上一步的输出但没正确传递
btn.click(fn=step1, inputs=[a], outputs=[b]) \
   .then(fn=step2, inputs=[c], outputs=[d])   # c 不是 b 的结果！

# ✅ 正确 — then 的 inputs 应该是上一步的 outputs
btn.click(fn=step1, inputs=[a], outputs=[b]) \
   .then(fn=step2, inputs=[b], outputs=[d])   # b 是 step1 的输出
```

---

### 陷阱 10：`gr.render` 用法错误

```python
# ❌ 静默失败 — 没有用 yield
@gr.render(inputs=[num])
def dynamic(n):
    for i in range(int(n)):
        gr.Textbox(label=f"字段{i}")    # 没有 yield，不会渲染

# ✅ 正确 — 必须用 yield
@gr.render(inputs=[num])
def dynamic(n):
    for i in range(int(n)):
        yield gr.Textbox(label=f"字段{i}")
```

---

### 陷阱 11：JS 注入时机问题

```python
# ❌ 静默失败 — JS 在 DOM 加载前执行，找不到元素
demo.launch(js='document.getElementById("my-btn").style.color="red"')

# ✅ 正确 — 等待 DOM 加载完成
demo.launch(js='''
    window.addEventListener('DOMContentLoaded', () => {
        document.getElementById("my-btn").style.color = "red";
    });
''')
```

---

### 陷阱 12：`footer_links` 写错（6.x 替代 `show_api`）

```python
# ❌ 静默失败 — show_api 在 6.x 被忽略，不报错
demo.launch(show_api=False)

# ❌ 静默失败 — footer_links 值写错
demo.launch(footer_links="api")           # 应该是列表
demo.launch(footer_links=["API"])        # 大小写错误

# ✅ 正确
demo.launch(footer_links=["api", "gradio", "settings"])
# 可选值只有三个："api" | "gradio" | "settings"
```

---

### 陷阱 13：`api_visibility` 写错

```python
# ❌ 静默失败 — 旧写法被忽略
btn.click(fn=fn, show_api=False)
btn.click(fn=fn, api_name=False)

# ❌ 静默失败 — 值写错
btn.click(fn=fn, api_visibility="hidden")     # 没有这个值
btn.click(fn=fn, api_visibility=False)        # 不接受布尔值

# ✅ 正确 — 只有三个有效值
btn.click(fn=fn, api_visibility="public")       # 公开（默认）
btn.click(fn=fn, api_visibility="undocumented") # 隐藏但可访问
btn.click(fn=fn, api_visibility="private")      # 完全禁用
```

---

### 陷阱 14：组件 `value` 类型不匹配

```python
# ❌ 静默失败 — Dataframe 的 value 类型不对
gr.Dataframe(value="1,2,3\n4,5,6")    # 字符串不自动解析

# ✅ 正确
gr.Dataframe(value=[[1,2,3],[4,5,6]])

# ❌ 静默失败 — Gallery 的 value 格式不对
gr.Gallery(value=["path/to/img.jpg"])  # 需要列表的列表

# ✅ 正确
gr.Gallery(value=[["path/to/img1.jpg"], ["path/to/img2.jpg"]])
```

---

### 6.x 关键易错对照表

| 易错点 | ❌ 错误写法 | ✅ 正确写法 |
|--------|-----------|-----------|
| 主题/CSS 位置 | `gr.Blocks(theme=..., css=...)` | `demo.launch(theme=..., css=...)` |
| Chatbot 消息格式 | `[["user", "bot"]]` | `[{"role":"user","content":"..."}]` |
| ChatInterface 示例 | `examples=[["你好","嗨"]]` | `examples=[{"role":"user","content":"你好"}]` |
| cache_examples | `cache_examples="lazy"` | `cache_examples=True, cache_mode="lazy"` |
| show_api | `launch(show_api=False)` | `launch(footer_links=["gradio"])` |
| show_api (事件) | `.click(show_api=False)` | `.click(api_visibility="undocumented")` |
| api_name=False | `.click(api_name=False)` | `.click(api_visibility="private")` |
| Dataframe 行数 | `row_count=(5, "fixed")` | `row_count=5, row_limits=(5,5)` |
| HTML padding | 默认有 padding | 默认无 padding，需手动 `padding=True` |
| like_user_message | `chatbot.like(..., like_user_message=True)` | `gr.Chatbot(like_user_message=True)` |
| Python 版本 | Python 3.9 | **Python ≥ 3.10** |

---

## 十六、快速排查清单

当你修改了代码但不生效时，按这个顺序检查：

| 序号 | 检查项 | 排查方法 |
|------|--------|---------|
| ① | `launch()` 参数位置 | `theme`/`css`/`js` 是否在 `launch()` 里？ |
| ② | CSS 选择器 | 组件是否有 `elem_id`？选择器是否匹配？ |
| ③ | 事件返回值 | 函数返回几个值？`outputs` 有几个组件？ |
| ④ | `inputs`/`outputs` | 是组件对象还是字符串？ |
| ⑤ | `visible` 修改 | 是否通过 `outputs` 返回 `gr.update(visible=...)`？ |
| ⑥ | Chatbot 格式 | 是否用了 `type="messages"` + 字典格式？ |
| ⑦ | ChatInterface 签名 | 函数是否是 `(message, history) -> str`？ |
| ⑧ | `gr.update()` | 属性名是否正确？该组件是否支持？ |
| ⑨ | `gr.render` | 是否用了 `yield`？ |
| ⑩ | JS 时机 | 是否等 DOM 加载完成？ |
| ⑪ | `footer_links` | 是否用列表？值是否为小写 `"api"/"gradio"/"settings"`？ |
| ⑫ | `api_visibility` | 值是否为 `"public"/"undocumented"/"private"`？ |
| ⑬ | 组件 `value` | 类型是否匹配（列表/字典/字符串）？ |

---

> **提示：把这份文件发给帮你改代码的 AI，让它每次修改后逐项对照检查，就能避免大部分"改了但不生效"的问题。**
