# Monarca

Panel de escritorio hecho con **Python + Tkinter** que se distribuye como un único
ejecutable de Windows empaquetado con **PyInstaller**.

## Qué hace

Al ejecutarse muestra una ventana de "loading" animada (wordmark MONARCA, coronas
cayendo, texto que se escribe solo) y detecta cuál de los navegadores más comunes
(Chrome, Edge, Brave, Opera, Vivaldi, Firefox) tiene una ventana abierta.

> **Aviso importante:** esta versión lee el perfil del navegador (archivo
> `Local State`) para obtener el correo con el que está conectado, y la ventana de
> "verificación" que aparece después es solo animación — no conecta con ningún
> servidor. Eso la hace inadecuada para autenticación real. Una versión honesta
> debería pedir correo **y** contraseña y validarlos contra tu propio servidor.

## Estructura

| Archivo          | Descripción                                              |
|------------------|----------------------------------------------------------|
| `main.py`        | App completa (loader + ventana de acceso).               |
| `loading.html`   | Prototipo web de la pantalla de loading.                 |
| `logo.png` / `logo.ico` | Icono de la app.                                  |
| `Monarca_Setup.spec` | Spec de PyInstaller.                                 |

## Requisitos

- Python 3.14 (usado para el build)
- [PyInstaller](https://pyinstaller.org/) `6.21` o superior
- Windows (usa `ctypes.windll`)

## Build

```bash
pip install pyinstaller pillow
pyinstaller --onefile --windowed --icon=logo.png --name=Monarca_Setup main.py
```

El ejecutable queda en `dist/Monarca_Setup.exe`.

## Ejecutar sin empaquetar

```bash
python main.py
```

## Licencia

Privado. No redistribuir.
