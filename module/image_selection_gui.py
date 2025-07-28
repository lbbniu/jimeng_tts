"""
图片选择GUI模块
"""

import os
import tkinter as tk
from tkinter import ttk
from typing import List, Dict
from dataclasses import dataclass
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

@dataclass
class SceneInfo:
    """场景信息"""
    scene_name: str
    original_text: str
    prompt: str
    image_files: List[str]
    audio_file: str
    subtitle_file: str


class ImageSelectionGUI:
    """图片选择GUI界面"""
    
    def __init__(self):
        self.selected_images = {}
    
    def show_selection_dialog(self, scenes: List[SceneInfo]) -> Dict[str, str]:
        """
        显示图片选择对话框
        
        Args:
            scenes: 场景信息列表
            
        Returns:
            选择的图片映射 {场景名: 图片路径}
        """
        # 创建主窗口
        root = tk.Tk()
        root.title("分镜图片选择")
        root.geometry("900x700")
        
        # 存储选择的图片
        self.selected_images = {}
        
        # 创建主框架
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # 配置主框架的网格权重
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # 配置根窗口的网格权重
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        
        # 创建滚动框架
        canvas = tk.Canvas(main_frame)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        # 绑定Canvas宽度变化，让scrollable_frame自适应宽度
        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.bind('<Configure>', on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 添加鼠标滚轮支持（跨平台兼容）
        def _on_mousewheel(event):
            # 检测操作系统类型
            import platform
            if platform.system() == "Darwin":  # macOS
                # 降低滚动速度，除以2让滚动更慢
                canvas.yview_scroll(int(-1*event.delta//2), "units")
            else:  # Windows/Linux
                # 降低滚动速度，除以2让滚动更慢
                canvas.yview_scroll(int(-1*(event.delta/120)//2), "units")
        
        # 直接绑定到canvas，不需要Enter/Leave事件
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        
        # 为每个场景创建选择界面
        for i, scene in enumerate(scenes):
            self._create_scene_selection_widget(scrollable_frame, scene, i)
        
        # 创建按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, pady=(10, 0))
        
        # 确定按钮
        confirm_button = ttk.Button(button_frame, text="确定", command=lambda: self._on_confirm(root))
        confirm_button.grid(row=0, column=3, padx=(10, 0))
        
        # 取消按钮
        cancel_button = ttk.Button(button_frame, text="取消", command=lambda: self._on_cancel(root))
        cancel_button.grid(row=0, column=2)
        
        # 运行GUI
        root.mainloop()
        
        return self.selected_images
    
    def _create_scene_selection_widget(self, parent, scene: SceneInfo, index: int):
        """为单个场景创建选择控件"""
        
        # 场景框架
        scene_frame = ttk.LabelFrame(parent, text=f"{scene.scene_name}", padding="10")
        scene_frame.grid(row=index, column=0, sticky="ew", pady=(0, 10), padx=(0, 10))
        scene_frame.columnconfigure(0, weight=1)
        
        # 配置父容器的网格权重，确保子组件能够扩展
        parent.columnconfigure(0, weight=1)
        
        # 原文
        ttk.Label(scene_frame, text="原文:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 5))
        text_widget = tk.Text(scene_frame, height=3, wrap=tk.WORD, 
                             background="#f0f0f0", foreground="#333333", 
                             relief="flat", borderwidth=1)
        text_widget.insert("1.0", scene.original_text)
        text_widget.config(state=tk.DISABLED)
        text_widget.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        
        # 提示词
        ttk.Label(scene_frame, text="提示词:", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(0, 5))
        prompt_widget = tk.Text(scene_frame, height=2, wrap=tk.WORD,
                               background="#f0f0f0", foreground="#333333", 
                               relief="flat", borderwidth=1)
        prompt_widget.insert("1.0", scene.prompt)
        prompt_widget.config(state=tk.DISABLED)
        prompt_widget.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        
        # 图片选择
        ttk.Label(scene_frame, text="选择图片:", font=("Arial", 10, "bold")).grid(row=4, column=0, sticky="w", pady=(0, 5))
        
        # 创建图片选择区域
        self._create_image_selection_area(scene_frame, scene.image_files, scene.scene_name)
    
    def _create_image_selection_area(self, parent, image_files: List[str], scene_name: str):
        """创建图片选择区域（带单选框和预览）"""
        
        # 创建图片选择变量
        selected_var = tk.StringVar()
        if image_files:
            selected_var.set(image_files[0])  # 默认选择第一张
        
        # 创建图片选择框架
        images_frame = ttk.Frame(parent)
        images_frame.grid(row=5, column=0, sticky="w", pady=(0, 5))
        images_frame.columnconfigure(0, weight=1)
        
        # 创建图片选择
        for i, img_path in enumerate(image_files):
            # 创建图片框架
            img_frame = ttk.Frame(images_frame)
            img_frame.grid(row=0, column=i, padx=(0, 15), pady=5, sticky="w")
            
            # 创建单选框
            radio = ttk.Radiobutton(img_frame, variable=selected_var, value=img_path)
            radio.grid(row=0, column=0, sticky="w")
            
            # 尝试显示图片缩略图
            try:
                from PIL import Image, ImageTk
                
                # 加载并缩放图片
                img = Image.open(img_path)
                img.thumbnail((240, 240), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                
                # 创建图片标签
                img_label = tk.Label(img_frame, image=photo)  # type: ignore
                img_label.image = photo  # 保持引用  # type: ignore
                img_label.grid(row=1, column=0, pady=(5, 0))
                
            except Exception as e:
                # 如果无法显示图片，创建占位符
                placeholder = tk.Label(img_frame, text=f"图片 {i+1}\n(无法预览)", 
                                      width=15, height=8, relief="solid")
                placeholder.grid(row=1, column=0, pady=(5, 0))
            
            # 图片名称
            img_name = os.path.basename(img_path)
            ttk.Label(img_frame, text=img_name, font=("Arial", 9)).grid(row=2, column=0, pady=(2, 0))
        
        # 保存选择
        def on_selection_change(*args):
            if selected_var.get():
                self.selected_images[scene_name] = selected_var.get()
        
        selected_var.trace_add("write", on_selection_change)
        
        # 初始化选择
        if image_files:
            self.selected_images[scene_name] = image_files[0]
    
    def _create_image_previews(self, parent, image_files: List[str], selected_var):
        """创建图片预览"""
        
        # 创建水平滚动的画布
        canvas = tk.Canvas(parent, height=200)
        scrollbar = ttk.Scrollbar(parent, orient="horizontal", command=canvas.xview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.TOP, fill=tk.X, expand=True)
        scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 创建图片预览
        for i, img_path in enumerate(image_files):
            # 创建图片框架
            img_frame = ttk.Frame(scrollable_frame)
            img_frame.pack(side=tk.LEFT, padx=(0, 10), pady=5)
            
            # 尝试显示图片缩略图
            try:
                from PIL import Image, ImageTk
                
                # 加载并缩放图片
                img = Image.open(img_path)
                img.thumbnail((120, 120), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                
                # 创建图片标签
                img_label = tk.Label(img_frame, image=photo)  # type: ignore
                img_label.image = photo  # 保持引用  # type: ignore
                img_label.pack()
                
            except Exception as e:
                # 如果无法显示图片，创建占位符
                placeholder = tk.Label(img_frame, text=f"图片 {i+1}\n(无法预览)", 
                                      width=15, height=8, relief="solid")
                placeholder.pack()
            
            # 图片编号
            ttk.Label(img_frame, text=f"图片 {i+1}", font=("Arial", 9, "bold")).pack()
            
            # 图片名称
            img_name = os.path.basename(img_path)
            if len(img_name) > 20:
                img_name = img_name[:17] + "..."
            ttk.Label(img_frame, text=img_name, font=("Arial", 8)).pack()
            
            # 文件大小信息
            try:
                size = os.path.getsize(img_path)
                size_mb = size / (1024 * 1024)
                ttk.Label(img_frame, text=f"{size_mb:.1f}MB", font=("Arial", 8), foreground="gray").pack()
            except OSError:
                pass
    
    def _on_confirm(self, root):
        """确认选择"""
        if not self.selected_images:
            try:
                import tkinter.messagebox as messagebox
                messagebox.showwarning("警告", "请至少选择一个图片")
            except ImportError:
                logger.warning("请至少选择一个图片")
            return
        
        logger.info(f"用户选择了 {len(self.selected_images)} 个图片")
        root.quit()
        root.destroy()
    
    def _on_cancel(self, root):
        """取消选择"""
        self.selected_images = {}
        logger.info("用户取消了选择")
        root.quit()
        root.destroy()
