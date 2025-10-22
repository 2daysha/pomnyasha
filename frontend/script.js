// Проверяем авторизацию при загрузке
async function checkAuth() {
  try {
      const response = await fetch('/me');
      const data = await response.json();
      
      if (data.authorized) {
          document.getElementById('loginBtn').textContent = 'Авторизован';
          document.getElementById('loginBtn').style.background = '#4CAF50';
      } else {
          document.getElementById('loginBtn').href = '/oauth2/login';
      }
  } catch (error) {
      console.error('Ошибка проверки авторизации:', error);
  }
}

// Запускаем при загрузке
document.addEventListener('DOMContentLoaded', checkAuth);