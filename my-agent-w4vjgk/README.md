# Rockers Asiste · Agente local con Phi-4-mini y MCP

Prototipo académico de atención y seguimiento de pedidos para Rockers. Combina un modelo de lenguaje ejecutado en **Foundry Local**, herramientas **MCP** de solo lectura y reglas programadas para consultar pedidos y responder preguntas comerciales.

Puedes probarlo con un Excel ficticio en tu computadora, sin acceder a la planilla de la organización. Los números y correos de la demostración son sintéticos: **no corresponden a clientes reales**.

## Qué permite hacer

- Consultar pedidos por número de venta (**NV**) o correo de compra.
- Elegir un pedido cuando un correo tiene varias compras.
- Interpretar etapas de fabricación y estados logísticos.
- Informar un rango estimado de cinco días hábiles y avisos de atraso.
- Responder preguntas sobre despachos, plazos generales, pagos, ubicación y otros temas de atención.
- Inspeccionar las llamadas a herramientas en Agent Inspector, incluido streaming.

No modifica pedidos, envía correos, agenda visitas ni transfiere conversaciones. Es un prototipo para pruebas internas; NV y correo identifican registros, pero no autentican al comprador.

## Cómo funciona

```text
Usuario / Agent Inspector
          ↓
Agente y control de consultas obligatorias
          ├─ MCP de pedidos → Excel local o XLSX compartido en Drive
          ├─ MCP de información → base comercial local en JSON
          └─ Phi-4-mini en Foundry Local → conversación general
```

`PedidosObligatorios` reconoce consultas de seguimiento y temas comerciales. Cuando corresponde, ejecuta la herramienta y presenta su resultado mediante respuestas controladas. El modelo atiende los mensajes que no resuelve esa capa. Una frase como «voy a consultar» no acredita una lectura: la evidencia es la llamada registrada en la traza.

La inferencia es local y no tiene una alternativa automática en la nube. La descarga inicial de dependencias y del modelo necesita internet; el modo Drive también lo necesita para actualizar pedidos. Los modos documentados no utilizan una API de Google ni un proveedor de inferencia de pago.

## Requisitos

- Windows y PowerShell, entorno utilizado en este proyecto.
- Python **3.13 o superior**, según `pyproject.toml`.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) para instalar las dependencias fijadas en `uv.lock`.
- [Foundry Local CLI](https://learn.microsoft.com/en-us/azure/foundry-local/how-to/how-to-use-foundry-local-cli), disponible como `foundry` en la terminal.
- El modelo `phi-4-mini` descargado y una variante compatible con el equipo.
- Opcional: Visual Studio Code y [Microsoft Foundry Toolkit, antes AI Toolkit](https://learn.microsoft.com/es-es/azure/foundry/how-to/develop/get-started-projects-vs-code), para usar Agent Inspector.

El equipo utilizado por el grupo cuenta con 16 GB de RAM y una RTX 4060 Laptop de 8 GB. Es una referencia del entorno de desarrollo, no un requisito mínimo ni una garantía de rendimiento para otros equipos.

## Inicio rápido con datos ficticios

### 1. Entrar a la carpeta del código

Desde la carpeta que contiene este README y `src`:

```powershell
cd .\src\agent-framework-agent-basic-responses
uv sync --frozen
foundry --version
foundry model download phi-4-mini
```

Los comandos restantes se ejecutan desde esa carpeta, donde está `main.py`. El proyecto utiliza el servidor REST de Foundry Local; no basta con tener otro proveedor de modelos instalado. Si tu versión de Foundry no reconoce un comando, consulta `foundry --help` y la documentación enlazada.

### 2. Configurar el entorno

```powershell
if (-not (Test-Path .env)) {
    Copy-Item .env.rockers.example .env
}
```

El archivo de ejemplo configura la demostración local:

```dotenv
FOUNDRY_LOCAL_MODEL=phi-4-mini
ROCKERS_LOCAL_ORDERS_MCP=1
ROCKERS_ORDERS_SOURCE=excel
ROCKERS_EXCEL_PATH=data/pedidos_demo.xlsx
ROCKERS_SHEET_TAB=Pedidos
ROCKERS_HEADER_ROW=2
ROCKERS_ENABLE_LEARN_MCP=0
```

Si ya tienes `.env`, el comando lo conserva. Para seguir esta demostración, ajusta manualmente esos valores y deja vacío `ROCKERS_ORDERS_MCP_URL` para no activar dos MCP de pedidos simultáneamente. No necesitas credenciales de Azure, claves de modelos de pago ni una cuenta de servicio de Google.

### 3. Crear el Excel de demostración

Pega el bloque completo en PowerShell. Crea siete filas de datos para seis números de pedido; uno de ellos aparece dos veces con estados contradictorios para probar la validación. Las fechas se generan hacia el futuro desde el día de ejecución.

```powershell
@'
from datetime import timedelta
from pathlib import Path
from openpyxl import Workbook
from orders_dates import hoy_lima

path = Path("data/pedidos_demo.xlsx")
if path.exists():
    raise SystemExit("El archivo de demostración ya existe; no se ha sobrescrito.")
path.parent.mkdir(parents=True, exist_ok=True)
wb = Workbook()
ws = wb.active
ws.title = "Pedidos"
ws.append(["DEMOSTRACION: DATOS FICTICIOS"])
ws.append(["NV", "Correo", "Produccion", "Estado Logistica"]
          + [f"Campo{i:02d}" for i in range(5, 20)] + ["Previsto"])
previsto = hoy_lima() + timedelta(days=14)
rows = [
    ("900001", "cliente001@example.com", "Corte", ""),
    ("900002", "cliente002@example.com", "Montaje", ""),
    ("900003", "cliente003@example.com", "Bodega", ""),
    ("900004", "cliente004@example.com", "Montaje", "Entregado"),
    ("900005", "cliente005@example.com", "Corte", ""),
    ("900005", "cliente005@example.com", "Montaje", ""),
    ("900006", "cliente001@example.com", "Pintura", ""),
]
for nv, correo, produccion, logistica in rows:
    ws.append([nv, correo, produccion, logistica] + [None] * 15 + [previsto])
wb.save(path)
wb.close()
print(f"Excel ficticio creado: {path.resolve()}")
'@ | uv run --frozen python -
```

La carpeta `data` está excluida de Git. Cada persona genera su propia demostración; no hace falta incluir la planilla de la organización en el repositorio.

### 4. Comprobar la lectura sin cargar el modelo

```powershell
uv run --frozen python -c "from orders_mcp import consultar_estado_pedido; print(consultar_estado_pedido(nv='900002'))"
```

Debe devolver `numero_pedido: 900002`, `estado: En producción` y una `fecha_aproximada` calculada desde el Excel. Esta comprobación llama a la función de consulta directamente: valida la lectura y las reglas, no una conversación ni el transporte MCP.

### 5. Iniciar el agente

```powershell
uv run --frozen python main.py
```

El inicio descubre el endpoint local de Foundry, inicia su servidor y carga el modelo configurado. El servidor de conversación utiliza **http://localhost:8088** por defecto. El puerto del modelo es distinto y se descubre automáticamente.

Abre Agent Inspector desde la extensión, conéctalo a ese servidor y selecciona el protocolo **Responses**. Para detener el proceso iniciado en la terminal, utiliza `Ctrl+C`.

**F5 en la estructura original:** abre la carpeta exterior que contiene `.vscode` y la subcarpeta `my-agent-w4vjgk`. Esa configuración inicia el agente en **8089**. Si distribuyes únicamente la carpeta interior con `src`, utiliza el inicio por terminal; no asumas que incluye la configuración exterior de depuración. Reinicia el proceso después de cambiar el código, `.env`, las instrucciones o el JSON comercial.

## Conversaciones para probar

Estos ejemplos funcionan con el Excel generado arriba. Las frases pueden variar; deben conservar el significado y los datos devueltos por las herramientas.

| Escribe en el chat | Resultado que debes comprobar |
| --- | --- |
| Hola, quiero consultar mi pedido. | Solicita amablemente el número de pedido o correo de compra. |
| Mi pedido es 900001. | Confirma que fue recibido y presenta un rango estimado. |
| ¿Cómo va mi pedido 900002? | Indica que está en producción. |
| Mi correo de compra es cliente002@example.com. | Localiza el pedido 900002. |
| Mi correo es cliente001@example.com. | Ofrece elegir entre 900001 y 900006; todavía no atribuye un estado a ambos. |
| 900006 | Consulta el pedido elegido y mantiene el correo del turno anterior. |
| Consulta mi pedido 900003. | Informa preparación final y próximo contacto. |
| Mi pedido es 900004. | Informa que figura como entregado; logística tiene prioridad sobre Montaje. |
| Consulta el pedido 900005. | Indica que la información necesita revisión; no elige arbitrariamente una de las filas. |
| Mi pedido es 999999. | Informa que no lo encontró y solicita revisar el dato. |

En el caso de selección, envía únicamente `900006` como siguiente mensaje. Para pruebas independientes utiliza **Clear Chat**. Revisa en las trazas que se ejecute `consultar_estado_pedido` antes de responder sobre una compra.

También puedes preguntar:

- ¿Hacen envíos a regiones?
- ¿Qué plazo tienen para fabricación y para pronta entrega?
- ¿Puedo pagar con tarjeta y pedir factura?
- ¿Dónde están ubicados?
- ¿Los muebles vienen armados?
- ¿Puedo agendar una visita o pedir un mueble a medida?
- Quiero hablar con un asesor.

Estas consultas utilizan `consultar_informacion_rockers`. Los plazos comerciales configurados son **7 a 10 días hábiles para fabricación** y **3 a 5 para pronta entrega**. Para identificar la modalidad, se pide revisar la descripción del producto comprado en [rockers.cl](https://rockers.cl). Esos plazos generales no sustituyen el rango calculado para un pedido concreto.

## Estructura del Excel

En la configuración de ejemplo, los encabezados están en la **fila 2** y la hoja se llama `Pedidos`.

| Campo | Ubicación y uso |
| --- | --- |
| `NV` | Número de pedido; conviene almacenarlo como texto para conservar ceros iniciales. |
| `Correo` | Correo completo para localizar compras. |
| `Produccion` | Etapa consolidada de fabricación. |
| `Estado Logistica` | Estado logístico; si está informado, tiene prioridad. |
| `Previsto` | Debe estar en la **columna T**, posición 20. Es la base de la estimación. |

No muevas `Previsto` a otra posición. Los encabezados `NV`, `Correo` y `Estado Logistica` deben conservar esa escritura; para `Produccion` se normalizan tildes y mayúsculas. Las columnas intermedias pueden existir sin ser utilizadas.

- El número se compara exactamente. No se eliminan puntos, separadores ni ceros iniciales; un valor numérico entero se convierte a texto sin `.0`.
- El correo se compara completo, ignorando mayúsculas y espacios externos.
- Varias líneas del mismo NV se consolidan si coinciden el estado final y la fecha calculada; si difieren, requieren revisión.
- Las fechas vacías o inválidas quedan pendientes de confirmar. La ausencia del encabezado `Previsto` en T es un error de estructura.
- `openpyxl` lee los valores guardados y no recalcula fórmulas. Si tu archivo las utiliza, guarda previamente sus resultados con una herramienta que las recalcule.
- La consulta no modifica ni guarda el archivo de origen.

## Estados y fechas

Si no hay estado logístico, se utiliza `Produccion`, no las marcas individuales Ok/No de otras columnas.

| Etapa | Mensaje al cliente |
| --- | --- |
| Corte | Pedido recibido correctamente. |
| Plegado, Partes y Piezas, Armado, Mig, Entregado a Pintura, Pintura, Montaje | Pedido en producción. |
| Stock Fabrica | Pedido recibido; se contactará al cliente cuando avance hacia la entrega. |
| Calidad o Bodega | Preparación final; deberían contactar al cliente en los próximos días. |
| Etapa vacía o sin regla definida | Estado pendiente de confirmar. |

El inicio del rango se calcula como **Previsto de T + 3 días hábiles**. El final es **inicio + 4 días hábiles**, formando cinco días hábiles inclusivos. Por ejemplo, si T es 14/10/2026, el rango es del **19 al 23 de octubre de 2026**.

Se cuentan lunes a viernes, sin un calendario de feriados. La comparación temporal usa UTC−5, hora de Lima. El rango es una estimación y no una promesa de entrega.

Si continúa en fabricación, se informa el atraso cuando faltan tres días hábiles o menos para el inicio, o ese inicio ya pasó. Solo se presenta todo el rango como vencido cuando pasó su fecha final. No se atribuye atraso de fabricación a pedidos listos para contacto, en despacho, entregados o cancelados.

## Conectar un XLSX compartido en Drive

Después de probar la demostración local, puedes utilizar un archivo propio autorizado. Cambia en `.env`:

```dotenv
ROCKERS_ORDERS_SOURCE=drive_xlsx
ROCKERS_SHEET_ID=ID_DE_TU_ARCHIVO
ROCKERS_HEADER_ROW=2
```

El ID es el segmento que aparece entre `/d/` y `/edit` en el enlace de la planilla. Sustituye el marcador por el ID de tu archivo; no se incluye aquí el de la organización.

Este adaptador descarga el XLSX mediante el enlace existente y lee **solo la primera hoja**, independientemente de `ROCKERS_SHEET_TAB`. Funciona únicamente si ese enlace ya permite descargar sin iniciar sesión. No evita permisos ni funciona con archivos restringidos que requieren autenticación. Para datos privados, mantén el modo Excel local o implementa un acceso autenticado adecuado.

El archivo se conserva en memoria, con caché de hasta **60 segundos**, y límite de **10 MB** por descarga. No se guarda una copia persistente. Si falla la actualización al caducar la caché, informa un error en lugar de reutilizar datos vencidos.

Para comprobar acceso y encabezados del archivo remoto, sin mostrar filas de clientes:

```powershell
uv run --frozen python check_orders.py
```

Ese comando es específico del modo Drive. No lo utilices como verificación del Excel local.

## Herramientas y archivos principales

Las herramientas MCP son:

- `consultar_estado_pedido(nv="", correo="")`: devuelve número, estado y fecha aproximada; con varios pedidos devuelve una lista para seleccionar.
- `consultar_informacion_rockers(tema)`: devuelve información comercial aprobada por tema.

| Archivo dentro de `src/agent-framework-agent-basic-responses` | Responsabilidad |
| --- | --- |
| `main.py` | Cliente local, integración del agente y servidor Responses. |
| `orders_mcp.py` | Servidor MCP de pedidos e información comercial. |
| `orders_guard.py` | Consultas obligatorias y redacción controlada de respuestas. |
| `orders_excel.py` / `orders_drive.py` | Lectura de las dos fuentes documentadas. |
| `orders_lookup.py` / `orders_dates.py` | Búsquedas, estados, validaciones y fechas. |
| `rockers_instructions.txt` | Instrucciones y límites del agente. |
| `rockers_faq.json` / `rockers_knowledge.py` | Información comercial y recuperación por tema. |
| `.env.rockers.example` | Configuración pública de ejemplo. |
| `tests/` | Pruebas automatizadas con datos ficticios. |

Microsoft Learn MCP es una opción técnica adicional. Se mantiene desactivado en el modo de atención mediante `ROCKERS_ENABLE_LEARN_MCP=0`. No es necesario para los ejemplos y no debe recibir datos de clientes.

## Pruebas y alcance de la validación

```powershell
uv run --frozen python -m unittest discover -s tests -v
```

Las pruebas automatizadas verifican lectura, búsqueda, fechas, estados, información comercial y configuración. Utilizan datos ficticios y no necesitan cargar Phi-4-mini ni consultar la planilla de la organización. No equivalen a una medición de exactitud conversacional, ahorro de tiempo o disponibilidad de producción; esas evaluaciones se realizan por separado con el agente en ejecución.

## Problemas frecuentes

| Problema | Qué revisar |
| --- | --- |
| `Foundry Local CLI is not installed or not on PATH` | Instala la CLI y abre una terminal nueva. Comprueba `foundry --version`. |
| `Local model is not configured` | Crea `.env` junto a `main.py` y configura `FOUNDRY_LOCAL_MODEL`. |
| `archivo_no_encontrado` | Comprueba `ROCKERS_EXCEL_PATH` y genera el archivo de demostración. |
| `estructura_no_valida` | Revisa hoja, fila de encabezados, nombres de columnas y `Previsto` en T. |
| `archivo_no_accesible` | En Drive, verifica el ID y que el enlace tenga el acceso requerido por este adaptador. |
| No encuentra un correo | Comprueba que esté completo y exista en `Correo`; un correo ficticio nuevo no crea un pedido automáticamente. |
| `requires ... tokens ... exceeds ... 4096` | El modelo necesita espacio para entrada y salida. El agente limita la generación a 768 tokens, pero un historial largo todavía puede superar el contexto. Usa **Clear Chat**; no hay reducción automática del historial implementada. |
| Inspector no conecta | Comprueba que el agente siga ejecutándose, el protocolo Responses y el puerto: 8088 por terminal, 8089 con la configuración exterior de F5. |
| Aparecen respuestas antiguas | Reinicia el agente y usa **Clear Chat**. En Drive espera también la caducidad de la caché. |

## Antes de publicar o adaptar

Incluye código, `uv.lock`, esta guía y la configuración de ejemplo. Conserva `.env`, planillas reales y credenciales fuera de Git. No publiques enlaces de acceso a archivos internos. Los ejemplos de esta guía utilizan únicamente correos `example.com` y pedidos ficticios.

Antes de atender clientes reales faltan verificación de identidad y autorización por pedido, controles de acceso al origen, despliegue y operación continua, y evaluación de conversaciones completas. Las respuestas ofrecen contactos para gestionar consultas; no acreditan stock, asesores conectados ni acciones que el agente no puede ejecutar.
