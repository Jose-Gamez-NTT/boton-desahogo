# Botón de desahogo

Una aplicación local para registrar desahogos sobre aplicativos y ver cómo evoluciona el ambiente. Los datos se guardan en SQLite en tu equipo, sin servicios externos ni dependencias adicionales de Python.

## Inicio

Necesitas Python 3.9 o superior. En Windows, ejecuta `iniciar.bat` con doble clic. También puedes arrancar desde una terminal:

```sh
python app.py
```

Se abrirá el navegador automáticamente. Mantén la ventana de la aplicación abierta mientras la utilices y pulsa `Ctrl+C` en ella para cerrarla. Si el navegador no se abre, visita la dirección que aparece en la terminal. Para usar un puerto libre automáticamente, ejecuta `python app.py --port 0`.

## Cómo funciona

Escribe tu desahogo y pulsa **Soltar desahogo**. El primer aplicativo es aXet.code y su icono se encuentra en `iconosAplicaciones/axet.png`. El termómetro muestra la actividad, no la disponibilidad real del sistema:

- Verde: 0 desahogos activos.
- Amarillo: 1–2.
- Naranja: 3–5.
- Rojo: 6 o más.

Desde que hay actividad, se descuenta un desahogo activo cada hora; los nuevos desahogos no reinician ese reloj. Cuando el contador llega a cero, se detiene hasta el próximo desahogo. El cálculo continúa aunque la aplicación esté cerrada y el historial se conserva íntegro.

La base de datos se encuentra en `datos/desahogos.sqlite3`. No está cifrada: cualquier persona con acceso a tu cuenta o a ese archivo puede leer su contenido. Para hacer una copia, cierra la aplicación y copia ese archivo. La carpeta de datos está excluida de Git.

## Pruebas

```sh
python -m unittest -v
```
