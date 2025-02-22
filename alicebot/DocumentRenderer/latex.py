from matplotlib import pyplot as plt
import matplotlib
import os
import sys
import fJson as fjson
from io import BytesIO
import regex
import base64
import traceback

from typing import Callable, Any

log_func: Callable[[Any], None]

# 添加MiKTeX的路径
__self_dir = os.path.dirname(os.path.abspath(__file__))
__config_dir = os.path.join(__self_dir, "config")
__config_path = os.path.join(__config_dir, "config.json")


@fjson.DataClass
class Config:
    def __init__(self):
        self.tex_path_win = ''
        self.tex_path_linux = ''
        self.tex_path_mac = ''

    def save(self, path: str):
        """保存配置到文件"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.json(indent=4, multi_line=True))

    @classmethod
    def load(cls, path: str):
        """从文件加载配置"""
        if not os.path.exists(path):
            return cls()

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = fjson.decode(f.read())
                config = cls()
                if data:
                    config.tex_path_win = data.get("tex_path_win", r"F:\MiKTeX\miktex\bin\x64\pdflatex.exe")
                    config.tex_path_linux = data.get("tex_path_linux", r"/usr/bin/pdflatex")
                    config.tex_path_mac = data.get("tex_path_mac", r"/Library/TeX/texbin/pdflatex")
                return config
        except Exception as e:
            log_func(f"[Config] Failed to load config: {e}")
            return cls()


if not os.path.exists(__config_dir):
    os.makedirs(__config_dir)
if not os.path.exists(__config_path):
    config = Config()
    config.save(__config_path)

config = Config.load(__config_path)

if sys.platform == "win32":
    tex_path = config.tex_path_win
    os.environ["PATH"] += os.pathsep + os.path.dirname(tex_path)
elif sys.platform == "linux":
    tex_path = config.tex_path_linux
    os.environ["PATH"] += os.pathsep + os.path.dirname(tex_path)
elif sys.platform == "darwin":
    tex_path = config.tex_path_mac
    os.environ["PATH"] += os.pathsep + os.path.dirname(tex_path)
else:
    log_func("Unknown platform")
    sys.exit(-1)

matplotlib.rc("font", family='STSong')
matplotlib.rcParams["font.sans-serif"] = ['Microsoft YaHei']
matplotlib.rc("axes", unicode_minus=False)
matplotlib.rc("axes", labelsize=12)
matplotlib.rc("xtick", labelsize=12)
matplotlib.rc("ytick", labelsize=12)
matplotlib.rc("legend", fontsize=12)
matplotlib.rc("figure", titlesize=12)
matplotlib.rc("figure", titleweight="bold")
matplotlib.rc("axes", titlesize=12)
matplotlib.rc("axes", titleweight="bold")
matplotlib.rc("font", weight="bold")
matplotlib.rc("axes", linewidth=1.5)
matplotlib.rc("lines", linewidth=1.5)
matplotlib.rc("lines", markersize=6)
matplotlib.rc("figure", figsize=(6, 4))
matplotlib.rc("figure", dpi=100)
matplotlib.rc("savefig", dpi=100)
matplotlib.rc("savefig", bbox="tight")
matplotlib.rc("savefig", pad_inches=0.1)
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
plt.rcParams['font.family'] = ['Microsoft YaHei']
plt.rc("text", usetex=True)
plt.rc(
    "text.latex",
    preamble=r"""
    \usepackage[utf8]{inputenc}
    \usepackage{amsmath}
    \usepackage{amsfonts}
    \usepackage{amssymb}
    \usepackage{bm}
    \usepackage{mathrsfs}
    \usepackage{upgreek}
    \usepackage{wasysym}
    \usepackage{physics}
    \usepackage{siunitx}
    \usepackage{mhchem}
    \usepackage{chemfig}
    \usepackage{chemformula}
    """
)


def get_formula_image_data(formula):
    try:
        # 创建一个图表
        fig = plt.figure(facecolor='white')
        fig.patch.set_alpha(1)

        # 在图表中添加文本
        txt = fig.text(0.5, 0.5, formula, ha='center', va='center', fontsize=20, color='black')

        # 将图表保存到BytesIO对象中
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=75, transparent=False, bbox_inches='tight', pad_inches=0.1)

        plt.close(fig)

        # 获取图像数据
        buf.seek(0)
        image_data = buf.getvalue()
        buf.close()
    except:
        log_func(f"[LaTeX]{traceback.format_exc()}")
        return None
    return image_data


def get_pie_chart_image_data(data, labels):
    try:
        # 创建一个图表
        fig = plt.figure(facecolor='white')
        fig.patch.set_alpha(1)

        # 在图表中添加饼图
        plt.pie(data, labels=labels, autopct='%1.1f%%', startangle=90, counterclock=False, shadow=True)
        plt.axis('equal')

        # 将图表保存到BytesIO对象中
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=75, transparent=False, bbox_inches='tight', pad_inches=0.1)

        plt.close(fig)

        # 获取图像数据
        buf.seek(0)
        image_data = buf.getvalue()
        buf.close()
    except:
        log_func(f"[LaTeX]{traceback.format_exc()}")
        return None
    return image_data


def format_LaTeX_to_png_ws(text) -> str:
    try:
        re = regex.compile(r"(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)|(?s)\$\$(.*?)\$\$")
        # 从文本中提取LaTeX公式, 并将其转换为图片(以base64编码的字符串形式), 然后替换为"Image_Base64:xxxxxx"
        # 如果是None, 则不替换
        # **保证get_formula_image_data只被调用一次**
        # 用循环遍历所有的公式

        result = text
        for m in re.finditer(text):
            formula = m.group()
            formula_ = formula
            log_func("[LaTeX]", formula)
            mul_line = False
            while formula.startswith("$$"):  # 将开头的$$换成$
                formula = formula[1:]
                mul_line = True
            while formula.endswith("$$"):
                formula = formula[:-1]
                mul_line = True
            if formula == "$":
                continue
            # if "\n" in formula and not mul_line:
            formula = formula.replace("\n", " ")
            # if mul_line:
            # formula = "$\n"+formula[1:-1]+"\n$"
            image_data = get_formula_image_data(formula)
            if image_data is not None:
                image_base64 = base64.b64encode(image_data).decode()
                result = result.replace(formula_, f" {formula_} \"Image_Base64:{image_base64}\" ")
    except:
        log_func(f"[LaTeX]{traceback.format_exc()}")
        return text
    return result


def format_LaTeX_to_png_CQ(text) -> str:
    try:
        re = regex.compile(r"(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)|(?s)\$\$(.*?)\$\$")
        # 从文本中提取LaTeX公式, 并将其转换为图片(以base64编码的字符串形式), 然后替换为"[CQ:image,file=base64://xxxxxx]"
        # 如果是None, 则不替换
        # **保证get_formula_image_data只被调用一次**
        # 用循环遍历所有的公式

        result = text
        for m in re.finditer(text):
            formula = m.group()
            formula_ = formula
            log_func("[LaTeX]", formula)
            while formula.startswith("$$"):  # 将开头的$$换成$
                formula = formula[1:]
            while formula.endswith("$$"):
                formula = formula[:-1]
            if formula == "$":
                continue
            formula = formula.replace("\n", " ")

            image_data = get_formula_image_data(formula)
            if image_data is not None:
                image_base64 = base64.b64encode(image_data).decode()
                result = result.replace(formula_, f" {formula_} [CQ:image,file=base64://{image_base64}] ")
    except:
        log_func(f"[LaTeX]{traceback.format_exc()}")
        return text
    return result
