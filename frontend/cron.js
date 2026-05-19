// Archivo: frontend/api/cron.js

export default async function handler(req, res) {
  try {
    // Hacemos la llamada POST a tu API de Render
    const response = await fetch('https://api-ml-7var.onrender.com/api/prediction/refresh', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
        // 'Authorization': `Bearer TU_TOKEN` // Descomenta esto si tu API en Render requiere autenticación
      }
    });

    const data = await response.json();

    // Respondemos a Vercel diciendo que todo ha ido bien
    return res.status(200).json({ success: true, message: "Llamada a Render exitosa", data });
    
  } catch (error) {
    console.error("Error al ejecutar el cron:", error);
    return res.status(500).json({ success: false, error: error.message });
  }
}