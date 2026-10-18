# Rockers Asiste · Agente local de atención y pedidos

Proyecto académico con **Phi-4-mini en Foundry Local**, Microsoft Agent Framework y herramientas **MCP** para consultar pedidos y responder preguntas comerciales.

La [guía completa de instalación y uso](my-agent-w4vjgk/README.md) incluye una demostración reproducible con Excel local, pedidos y correos ficticios, conversaciones de ejemplo, reglas de entrega y solución de errores frecuentes.

## Empezar

1. Sigue los requisitos de la [guía](my-agent-w4vjgk/README.md#requisitos).
2. Entra a la carpeta del código:

   ```powershell
   cd .\my-agent-w4vjgk\src\agent-framework-agent-basic-responses
   uv sync --frozen
   ```

3. Continúa con la [configuración y creación del Excel ficticio](my-agent-w4vjgk/README.md#inicio-rápido-con-datos-ficticios).
4. Inicia con `uv run --frozen python main.py` y conecta Agent Inspector a `http://localhost:8088`, protocolo Responses.

Si abres esta carpeta exterior en VS Code y utilizas la configuración existente de **F5**, el puerto es **8089**. Prepara primero las dependencias, `.env` y los datos siguiendo la guía.

La inferencia es local; consultar un XLSX remoto requiere internet. El prototipo lee datos y no modifica pedidos, envía correos ni transfiere conversaciones. Los ejemplos no contienen datos de clientes reales.

> El prototipo está destinado a pruebas internas. Consultar por número o correo no verifica la identidad del comprador; se requiere autorización antes de ofrecer acceso público.
