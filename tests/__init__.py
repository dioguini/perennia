"""Os testes nunca escrevem na pasta `data/` do projeto (os teus dados): cada execução usa uma
pasta de dados temporária (ver perennia.datadir)."""
import os
import tempfile

if not os.environ.get("PERENNIA_DATA_DIR"):
    os.environ["PERENNIA_DATA_DIR"] = tempfile.mkdtemp(prefix="perennia-testes-")

# as caches curtas (o programa do GarminDB, as versões) ficam desligadas: os testes mudam o
# ambiente entre chamadas
os.environ.setdefault("PERENNIA_CLI_CACHE_S", "0")
