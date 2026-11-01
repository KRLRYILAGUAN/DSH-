@echo off
rem Start the neuron-memory viewer at logon, independent of DSH and of the
rem plugin package (so plugin updates can replace node_modules freely).
cd /d "D:\DeepSeek harness工作区\AI神经元记忆框架"
".venv\Scripts\pythonw.exe" -m viewer.server --db "D:\DeepSeek harness工作区\.neuron-memory\neuron.db" --port 8420
