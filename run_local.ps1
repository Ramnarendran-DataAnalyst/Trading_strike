# Install dependencies and start the app at http://127.0.0.1:8501
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} else {
    throw "Python 3.10 or later is required."
}

& $python -m pip install -r requirements.txt
& $python -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
