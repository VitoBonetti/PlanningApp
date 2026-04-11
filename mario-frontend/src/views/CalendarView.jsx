import React, { useState, useMemo } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import HolidayModal from '../components/Modals/HolidayModal';

// --- A palette of visually distinct colors for different team members ---
const USER_COLORS = [
  { bg: '#e0f2fe', text: '#0369a1' }, // Sky Blue
  { bg: '#dcfce7', text: '#15803d' }, // Green
  { bg: '#fef9c3', text: '#a16207' }, // Yellow
  { bg: '#ffedd5', text: '#c2410c' }, // Orange
  { bg: '#fce7f3', text: '#be185d' }, // Pink
  { bg: '#e0e7ff', text: '#4338ca' }, // Indigo
  { bg: '#ccfbf1', text: '#0f766e' }, // Teal
  { bg: '#f4f4f5', text: '#3f3f46' }, // Zinc
  { bg: '#fae8ff', text: '#86198f' }, // Fuchsia
  { bg: '#ffe4e6', text: '#9f1239' }, // Rose
  { bg: '#ede9fe', text: '#5b21b6' }, // Violet
  { bg: '#cffafe', text: '#0e7490' }, // Cyan
  { bg: '#ecfccb', text: '#4d7c0f' }, // Lime
  { bg: '#fef3c7', text: '#b45309' }, // Amber
  { bg: '#dbeafe', text: '#1d4ed8' }, // Blue
  { bg: '#f1f5f9', text: '#334155' }  // Slate
];

// --- Sequential Matcher: Guarantees 100% unique colors! ---
const getUserColor = (userId, pentestersArray) => {
  if (!userId || !pentestersArray) return USER_COLORS[0];
  const userIndex = pentestersArray.findIndex(p => p.id === userId);
  const safeIndex = userIndex === -1 ? 0 : userIndex;
  return USER_COLORS[safeIndex % USER_COLORS.length];
};

const CalendarView = ({ boardData, fetchBoard, currentUser, setConfirmAction }) => {
  const [currentDate, setCurrentDate] = useState(new Date());
  
  // Modal State
  const [modalOpen, setModalOpen] = useState(false);
  const [activeHoliday, setActiveHoliday] = useState(null);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();
  const monthName = currentDate.toLocaleString('default', { month: 'long' });

  const handlePrevMonth = () => setCurrentDate(new Date(year, month - 1, 1));
  const handleNextMonth = () => setCurrentDate(new Date(year, month + 1, 1));
  const handleToday = () => setCurrentDate(new Date());

  const toDateStr = (d) => {
    if (!d) return "";
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };

  const extractDateStr = (dateInput) => {
    if (!dateInput) return "";
    return String(dateInput).split('T')[0];
  };

  const weeks = useMemo(() => {
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const weeksArray = [];
    let currentWeek = [];

    const firstDayOfMonth = new Date(year, month, 1).getDay();
    const padDays = (firstDayOfMonth === 0 || firstDayOfMonth === 6) ? 0 : firstDayOfMonth - 1;
    
    for (let i = 0; i < padDays; i++) currentWeek.push(null);

    for (let day = 1; day <= daysInMonth; day++) {
      const date = new Date(year, month, day);
      const dayOfWeek = date.getDay();

      if (dayOfWeek !== 0 && dayOfWeek !== 6) { 
        currentWeek.push(date);
      }

      if (dayOfWeek === 5) {
        weeksArray.push(currentWeek);
        currentWeek = [];
      }
    }
    
    if (currentWeek.length > 0) {
      while (currentWeek.length < 5) currentWeek.push(null);
      weeksArray.push(currentWeek);
    }

    return weeksArray;
  }, [year, month]);

  const events = boardData?.events || boardData?.holidays || [];
  const pentesters = boardData?.pentesters || [];

  const calculateEventCredits = (event, user) => {
    const eType = event.event_type || event.type;
    
    let workingDays = 0;
    const eStart = extractDateStr(event.start_date || event.start);
    const eEnd = extractDateStr(event.end_date || event.end);
    let d = new Date(`${eStart}T12:00:00`);
    const end = new Date(`${eEnd}T12:00:00`);
    
    while (d <= end) {
      if (d.getDay() !== 0 && d.getDay() !== 6) workingDays++;
      d.setDate(d.getDate() + 1); 
    }

    if (eType === 'national_holiday' || eType === 'team_day') {
      const loc = event.location || 'Global';
      const affectedUsers = pentesters.filter(p => loc === 'Global' || p.location === loc);
      
      let totalDailyCap = 0;
      affectedUsers.forEach(p => {
         const c = Number(p.capacity !== undefined ? p.capacity : (p.base_capacity || 1.0));
         totalDailyCap += (c / 5);
      });
      
      if (totalDailyCap === 0) return null;
      return (workingDays * totalDailyCap).toFixed(1);
    }

    if (!user) return null;
    
    const baseCap = Number(user.capacity !== undefined ? user.capacity : (user.base_capacity || 1.0));
    if (baseCap === 0) return null;
    
    const dailyCapacity = baseCap / 5;
    return (workingDays * dailyCapacity).toFixed(1);
  };

  return (
    <div style={{ padding: '24px', height: 'calc(100vh - 75px)', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', animation: 'fadeIn 0.3s ease' }}>
      
      {/* Header Controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h2 style={{ margin: 0, fontSize: '24px', color: '#0f172a' }}>{monthName} {year}</h2>
          <button className="btn-secondary" onClick={handleToday} style={{ padding: '6px 12px', fontSize: '13px' }}>Today</button>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button className="btn-secondary" onClick={handlePrevMonth}>◀ Prev</button>
          <button className="btn-secondary" onClick={handleNextMonth}>Next ▶</button>
        </div>
      </div>

      {/* Main Grid Container */}
      <div style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', border: '1px solid #e2e8f0', borderRadius: '8px', overflow: 'hidden', backgroundColor: 'white', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}>
        
        {/* Days Header */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', borderBottom: '1px solid #e2e8f0', backgroundColor: '#f8fafc', flexShrink: 0 }}>
          {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'].map(day => (
            <div key={day} style={{ padding: '12px', textAlign: 'center', fontWeight: 'bold', color: '#475569', fontSize: '14px', borderRight: '1px solid #e2e8f0' }}>{day}</div>
          ))}
        </div>

        {/* Calendar Body */}
        <div style={{ flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
          {weeks.map((week, weekIdx) => {
            
            const refDay = week.find(d => d !== null);
            const refIdx = week.indexOf(refDay);

            const trueWeekStart = new Date(refDay);
            trueWeekStart.setDate(refDay.getDate() - refIdx);
            const trueWeekStartStr = toDateStr(trueWeekStart);

            const trueWeekEnd = new Date(refDay);
            trueWeekEnd.setDate(refDay.getDate() - refIdx + 4);
            const trueWeekEndStr = toDateStr(trueWeekEnd);

            const weekEvents = events.filter(evt => {
              const eStart = extractDateStr(evt.start_date || evt.start);
              const eEnd = extractDateStr(evt.end_date || evt.end);
              return eStart <= trueWeekEndStr && eEnd >= trueWeekStartStr;
            });

            return (
              <div key={weekIdx} style={{ flexGrow: 1, flexBasis: 0, position: 'relative', display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', borderBottom: '1px solid #e2e8f0' }}>
                
                {/* Background Day Cells */}
                {week.map((day, dayIdx) => (
                  <div 
                    key={dayIdx} 
                    onClick={() => {
                      if (!day) return;
                      const dStr = toDateStr(day);
                      const currentUserId = currentUser?.id || '';
                      const defaultUserId = currentUser?.role === 'admin' ? '' : currentUserId;
                      setActiveHoliday({ 
                        event_type: 'personal_holiday', 
                        user_id: '', 
                        location: 'Global', 
                        start_date: dStr, 
                        end_date: dStr 
                      });
                      setModalOpen(true);
                    }}
                    style={{ 
                      borderRight: '1px solid #e2e8f0', 
                      padding: '8px', 
                      backgroundColor: !day ? '#f8fafc' : 'transparent',
                      cursor: day ? 'pointer' : 'default'
                    }}
                  >
                    {day && (
                      <span style={{ 
                        display: 'inline-block', width: '28px', height: '28px', textAlign: 'center', lineHeight: '28px', borderRadius: '50%',
                        backgroundColor: toDateStr(day) === toDateStr(new Date()) ? '#2563eb' : 'transparent',
                        color: toDateStr(day) === toDateStr(new Date()) ? 'white' : '#64748b',
                        fontWeight: toDateStr(day) === toDateStr(new Date()) ? 'bold' : 'normal'
                      }}>
                        {day.getDate()}
                      </span>
                    )}
                  </div>
                ))}

                {/* Foreground Event Bars */}
                <div style={{ position: 'absolute', top: '40px', left: 0, right: 0, bottom: '5px', pointerEvents: 'none', display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gridAutoRows: 'min-content', rowGap: '4px', overflowY: 'auto' }}>
                  {weekEvents.map((evt, evtIdx) => {
                    const eStart = extractDateStr(evt.start_date || evt.start);
                    const eEnd = extractDateStr(evt.end_date || evt.end);
                    const eType = evt.event_type || evt.type;
                    
                    let startCol = null;
                    let endCol = null; 

                    for (let idx = 0; idx < 5; idx++) {
                      const cellDate = new Date(trueWeekStart);
                      cellDate.setDate(trueWeekStart.getDate() + idx);
                      const cellDateStr = toDateStr(cellDate);

                      if (cellDateStr >= eStart && cellDateStr <= eEnd) {
                        if (startCol === null) startCol = idx + 1; 
                        endCol = idx + 2; 
                      }
                    }

                    if (startCol === null) return null;

                    const user = pentesters.find(p => p.id === evt.user_id);
                    const creditsUsed = calculateEventCredits(evt, user);
                    
                    let label = user?.name || 'Unknown User';
                    
                    let bgCol, textCol;

                    if (eType === 'national_holiday') {
                      bgCol = '#fee2e2'; textCol = '#b91c1c'; 
                      label = `🌍 National Holiday (${evt.location || 'Global'})`;
                    } else if (eType === 'team_day') {
                      bgCol = '#f3e8ff'; textCol = '#7e22ce'; 
                      label = `🚀 Team Day`;
                    } else {
                      const colorProfile = getUserColor(user?.id, pentesters);
                      bgCol = colorProfile.bg;
                      textCol = colorProfile.text;
                    }

                    const isAdmin = currentUser?.role === 'admin';
                    const isOwner = String(user?.id) === String(currentUser?.id);
                    const canEdit = isAdmin || (eType !== 'national_holiday' && eType !== 'team_day' && isOwner);

                    const tooltipText = creditsUsed !== null 
                      ? `${label} | Credits Utilized: ${creditsUsed}`
                      : label;

                    return (
                      <div 
                        key={evt.id || evtIdx} 
                        title={tooltipText}
                        onClick={(e) => {
                          e.stopPropagation(); 
                          if (!canEdit) return;
                          setActiveHoliday({
                            id: evt.id,
                            event_type: evt.event_type || evt.type,
                            user_id: evt.user_id || '',
                            location: evt.location || 'Global',
                            start_date: extractDateStr(evt.start_date || evt.start),
                            end_date: extractDateStr(evt.end_date || evt.end)
                          });
                          setModalOpen(true);
                        }}
                        style={{
                          gridColumn: `${startCol} / ${endCol}`,
                          backgroundColor: bgCol, color: textCol,
                          padding: '4px 8px', borderRadius: '4px', fontSize: '12px', fontWeight: 'bold',
                          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                          pointerEvents: 'auto', cursor: 'pointer',
                          margin: '0 4px', 
                          borderLeft: startCol !== 1 || eStart >= trueWeekStartStr ? `3px solid ${textCol}` : 'none'
                        }}
                      >
                        {label} {creditsUsed !== null && `(-${creditsUsed} cr)`}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        {/* --- THE MODAL IS RENDERED HERE --- */}
        <HolidayModal 
          isOpen={modalOpen}
          onClose={() => setModalOpen(false)}
          holidayData={activeHoliday}
          setHolidayData={setActiveHoliday}
          pentesters={pentesters}
          currentUser={currentUser}
          
          onSave={async () => {
            try {
              const payload = {
                event_type: activeHoliday.event_type,
                location: activeHoliday.location,
                start_date: activeHoliday.start_date,
                end_date: activeHoliday.end_date,
                user_id: activeHoliday.event_type === 'national_holiday' ? null : activeHoliday.user_id
              };

              if (activeHoliday.id) {
                await axios.put(`/api/events/${activeHoliday.id}`, payload);
                toast.success("Holiday updated!");
              } else {
                await axios.post('/api/events/', payload);
                toast.success("Holiday added!");
              }

              setModalOpen(false);
              if (fetchBoard) fetchBoard();
              
            } catch (err) {
              toast.error(err.response?.data?.detail || "Failed to save holiday.");
            }
          }}

          onDelete={async (id) => {
            setConfirmAction({
              isOpen: true,
              message: "Are you sure you want to completely delete this time off?",
              onConfirm: async () => {
                try {
                  await axios.delete(`/api/events/${id}`);
                  toast.success("Holiday deleted!");
                  setModalOpen(false);
                  if (fetchBoard) fetchBoard();
                } catch (err) {
                  toast.error(err.response?.data?.detail || "Failed to delete holiday.");
                }
                setConfirmAction({ isOpen: false });
              }
            });
          }}
        />

      </div>
    </div>
  );
};

export default CalendarView;