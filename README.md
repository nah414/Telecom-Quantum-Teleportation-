# Telecom-Quantum-Teleportation-
Using photonics and fiber optics to transfer entangled states. Windows version.
# 1) Unpack
Expand-Archive -Force .\Quantum-Interconnect-Hybrid-Mode.zip .

# 2) Move contents up if they landed in a subfolder (likely "quantum-interconnect-hybrid")
#    This moves all files/folders from the subdir into the repo root.
robocopy .\quantum-interconnect-hybrid . /E /MOVE

# 3) Stop tracking the zip, and ignore it going forward
git rm --cached Quantum-Interconnect-Hybrid-Mode.zip
echo "Quantum-Interconnect-Hybrid-Mode.zip" >> .gitignore

# 4) Commit the real tree
git add .
git commit -m "unpack: materialize source tree; remove binary blob"
git push
Gitbash, linux, MacOS version
unzip -o Quantum-Interconnect-Hybrid-Mode.zip
rsync -a quantum-interconnect-hybrid/ ./
rm -rf quantum-interconnect-hybrid
git rm --cached Quantum-Interconnect-Hybrid-Mode.zip
printf "Quantum-Interconnect-Hybrid-Mode.zip\n" >> .gitignore
git add .
git commit -m "unpack: materialize source tree; remove binary blob"
git push
python -m pip install --upgrade pip
pip install -r requirements.txt
pre-commit install
pre-commit run --all-files || true
pytest -q
mkdocs build --strict
# IBM Runtime
export QISKIT_IBM_TOKEN="<your_api_key>"
python scripts/configure_ibm.py

# AWS Braket (IonQ/Rigetti/IQM)
aws configure   # if not already configured
python scripts/check_braket.py

