import React from 'react';
import './StatisticsPage.css';

const StatisticsPage = ({ onBack }) => {
  // Mock данные для круговой диаграммы
  const categoryData = [
    { name: 'Друзья', value: 25, color: '#FF6B6B' },
    { name: 'Семья', value: 30, color: '#4ECDC4' },
    { name: 'Работа', value: 35, color: '#45B7D1' },
    { name: 'Быт', value: 10, color: '#FFA07A' }
  ];

  const dayData = [
    { day: 'ПОНЕДЕЛЬНИК', tasks: 8, isMostBusy: true },
    { day: 'ВТОРНИК', tasks: 6, isMostBusy: false },
    { day: 'СРЕДА', tasks: 5, isMostBusy: false },
    { day: 'ЧЕТВЕРГ', tasks: 7, isMostBusy: false },
    { day: 'ПЯТНИЦА', tasks: 4, isMostBusy: false },
    { day: 'СУББОТА', tasks: 3, isMostBusy: false },
    { day: 'ВОСКРЕСЕНЬЕ', tasks: 2, isMostBusy: false }
  ];

  const mostBusyDay = dayData.find(day => day.isMostBusy);

  // Функция для создания круговой диаграммы
  const renderPieChart = () => {
    let currentAngle = 0;
    
    return categoryData.map((category, index) => {
      const angle = (category.value / 100) * 360;
      const startAngle = currentAngle;
      const endAngle = currentAngle + angle;
      currentAngle = endAngle;

      // Координаты для SVG path
      const startX = 100 + 80 * Math.cos((startAngle - 90) * (Math.PI / 180));
      const startY = 100 + 80 * Math.sin((startAngle - 90) * (Math.PI / 180));
      const endX = 100 + 80 * Math.cos((endAngle - 90) * (Math.PI / 180));
      const endY = 100 + 80 * Math.sin((endAngle - 90) * (Math.PI / 180));

      const largeArcFlag = angle > 180 ? 1 : 0;

      const pathData = [
        `M 100 100`,
        `L ${startX} ${startY}`,
        `A 80 80 0 ${largeArcFlag} 1 ${endX} ${endY}`,
        'Z'
      ].join(' ');

      return (
        <g key={category.name}>
          <path
            d={pathData}
            fill={category.color}
            stroke="#FFF9DA"
            strokeWidth="2"
          />
          {/* Текст с процентами в центре сегмента */}
          <text
            x={100 + 40 * Math.cos((startAngle + angle/2 - 90) * (Math.PI / 180))}
            y={100 + 40 * Math.sin((startAngle + angle/2 - 90) * (Math.PI / 180))}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="white"
            fontSize="12"
            fontWeight="bold"
            className="pie-percentage"
          >
            {category.value}%
          </text>
        </g>
      );
    });
  };

  return (
    <div className="statistics-page">
      {/* Шапка - только кнопка назад */}
      <header className="stats-header">
        <button className="back-button" onClick={onBack}>
          ← Вернуться назад
        </button>
      </header>

      <div className="stats-content">
        {/* Круговая диаграмма */}
        <div className="stats-section">
          <h2>Статистика</h2>
          <div className="pie-chart-container">
            <svg width="200" height="200" viewBox="0 0 200 200" className="pie-chart">
              {renderPieChart()}
              {/* Центральный круг */}
              <circle cx="100" cy="100" r="30" fill="#FFF9DA" />
            </svg>
            
            {/* Легенда */}
            <div className="pie-legend">
              {categoryData.map((category, index) => (
                <div key={category.name} className="legend-item">
                  <div 
                    className="legend-color" 
                    style={{ backgroundColor: category.color }}
                  ></div>
                  <span className="legend-name">{category.name}</span>
                  <span className="legend-value">{category.value}%</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Статистика по дням недели */}
        <div className="stats-section">
          <h2>Загруженность по дням недели</h2>
          <div className="days-stats">
            {dayData.map(day => (
              <div 
                key={day.day} 
                className={`day-item ${day.isMostBusy ? 'most-busy' : ''}`}
              >
                <span className="day-name">{day.day}</span>
                <div className="day-tasks">
                  <span className="tasks-count">{day.tasks} задач</span>
                  <div 
                    className="tasks-bar"
                    style={{ width: `${(day.tasks / 10) * 100}%` }}
                  ></div>
                </div>
              </div>
            ))}
          </div>
          
          {/* Самый загруженный день */}
          {mostBusyDay && (
            <div className="most-busy-day">
              <div className="most-busy-badge">Самый загруженный день</div>
              <div className="most-busy-content">
                <span className="most-busy-name">{mostBusyDay.day}</span>
                <span className="most-busy-tasks">{mostBusyDay.tasks} задач</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StatisticsPage;