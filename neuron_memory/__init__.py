"""AI 神经元记忆框架 —— M1 原型。

四个动词：remember / recall / forget / consolidate。
"""

from .memory import NeuronMemory, default_db_path

__version__ = "0.1.0"
__all__ = ["NeuronMemory", "default_db_path", "__version__"]
