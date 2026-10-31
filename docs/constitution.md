# Constitución — Diario de Estudio
Principios innegociables. Toda spec, plan y tarea debe cumplirlos.
1. **Simplicidad primero**: el codigo debe ser sencillo legible con los comentarios necesarios en castellano.
   Debes mantenener la estructura del proyecto. Unicamete añadir el código necesario con los mínimos cambios necesarios en el pipeline de la estructura pricipal.
2. **La spec manda**: nada se implementa si no está en la spec activa. Si falta una
decisión, se para y se pregunta.
1. **Lógica separada de interfaz**: los cálculos (fechas, rachas, estadísticas) son
funciones puras, sin DOM ni localStorage, que reciben "hoy" como parámetro.
1. **Tests como puerta**: la lógica se prueba con `node --test`, sin instalar paquetes.
Prohibido avanzar con tests en rojo.
1. **Los datos del usuario son sagrados**: localStorage con compatibilidad hacia atrás y
fechas siempre en hora local. Nunca se pierde una sesión.
1. **Idioma**: código en inglés; interfaz y documentación en español. 