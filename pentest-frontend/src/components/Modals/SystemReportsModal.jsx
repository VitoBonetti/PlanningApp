import React from 'react';

const modalBackdropStyle = { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(15, 23, 42, 0.4)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, animation: 'fadeIn 0.2s ease-out' };
const modalContentStyle = { backgroundColor: 'white', padding: '32px', borderRadius: '12px', color: '#334155', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)', animation: 'slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)', border: '1px solid #e2e8f0', width: '800px', maxHeight: '85vh', overflowY: 'auto' };
const closeButtonStyle = { backgroundColor: '#e2e8f0', color: '#333', border: 'none', padding: '10px 20px', borderRadius: '4px', cursor: 'pointer' };

const SystemReportsModal = ({
  isOpen,
  onClose,
  boardData,
  currentUser,
  openEditHolidayModal,
  handleDeleteHoliday,
  handleWipeSystem
}) => {
  if (!isOpen || !boardData) return null;

  // We moved this helper function OUT of App.jsx and into here!
  const getWorkingDays = (startDate, endDate) => {
    const start = new Date(startDate + 'T00:00:00');
    const end = new Date(endDate + 'T00:00:00');
    let count = 0;
    let current = new Date(start);

    while (current <= end) {
      const dayOfWeek = current.getDay();
      if (dayOfWeek !== 0 && dayOfWeek !== 6) {
        count++;
      }
      current.setDate(current.getDate() + 1);
    }
    return count;
  };

  return (
    <div style={modalBackdropStyle}>
      <div style={modalContentStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h2 style={{ margin: 0 }}>System Reports</h2>
          <button style={closeButtonStyle} onClick={onClose}>Close</button>
        </div>

        {/* SECTION 1: USERS */}
        <h3 style={{ borderBottom: '2px solid #e2e8f0', paddingBottom: '5px' }}>Team Directory</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '30px', fontSize: '0.9rem' }}>
          <thead>
            <tr style={{ backgroundColor: '#f8fafc', borderBottom: '2px solid #cbd5e1' }}>
              <th style={{ padding: '10px', textAlign: 'left' }}>Name</th>
              <th style={{ padding: '10px', textAlign: 'left' }}>Role</th>
              <th style={{ padding: '10px', textAlign: 'left' }}>Location</th>
              <th style={{ padding: '10px', textAlign: 'left' }}>Base Capacity</th>
            </tr>
          </thead>
          <tbody>
            {boardData.pentesters.filter(p => p.role !== 'read_only').map(p => (
              <tr key={p.id} style={{ borderBottom: '1px solid #e2e8f0' }}>
                <td style={{ padding: '10px', textAlign: 'left', fontWeight: 'bold' }}>{p.name}</td>
                <td style={{ padding: '10px', textAlign: 'left', textTransform: 'capitalize' }}>{p.role}</td>
                <td style={{ padding: '10px', textAlign: 'left' }}>{p.location}</td>
                <td style={{ padding: '10px', textAlign: 'left' }}>{p.capacity} cr/wk</td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* SECTION 2: HOLIDAYS */}
        <h3 style={{ borderBottom: '2px solid #e2e8f0', paddingBottom: '5px' }}>Holidays & Time Off</h3>
        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: '30px', fontSize: '0.9rem' }}>
          <thead>
            <tr style={{ backgroundColor: '#f8fafc', borderBottom: '2px solid #cbd5e1' }}>
              <th style={{ padding: '10px', textAlign: 'left' }}>Type</th>
              <th style={{ padding: '10px', textAlign: 'left' }}>Who / Where</th>
              <th style={{ padding: '10px', textAlign: 'left' }}>Start Date</th>
              <th style={{ padding: '10px', textAlign: 'left' }}>End Date</th>
              <th style={{ padding: '10px', textAlign: 'left' }}>Working Days</th>
              <th style={{ padding: '10px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {boardData.events.map(e => (
              <tr key={e.id} style={{ borderBottom: '1px solid #e2e8f0' }}>
                <td style={{ padding: '10px', textAlign: 'left' }}>{e.type === 'team_day' ? '🚀 Team Day' : (e.type === 'national_holiday' ? '🌍 National Holiday' : '🏖 Personal')}</td>
                <td style={{ padding: '10px', textAlign: 'left', fontWeight: 'bold' }}>{e.type === 'national_holiday' ? e.location : e.user_name}</td>
                <td style={{ padding: '10px', textAlign: 'left' }}>{e.start}</td>
                <td style={{ padding: '10px', textAlign: 'left' }}>{e.end}</td>
                <td style={{ padding: '10px', textAlign: 'left', fontWeight: 'bold', color: '#b45309' }}>{getWorkingDays(e.start, e.end)} day(s)</td>
                <td style={{ padding: '10px', textAlign: 'right' }}>
                   <button className="btn-primary" onClick={() => openEditHolidayModal(e)} title="Edit">✏️</button>
                   <button className="btn-danger" onClick={() => handleDeleteHoliday(e.id)} title="Delete">🗑️</button>
                </td>
              </tr>
            ))}
            {boardData.events.length === 0 && <tr><td colSpan="6" style={{ padding: '10px', textAlign: 'center', color: '#666' }}>No events recorded.</td></tr>}
          </tbody>
        </table>

        {/* Admin Danger Zone */}
        {currentUser?.role === 'admin' && (
          <div style={{ marginTop: '40px', paddingTop: '20px', borderTop: '2px dashed #ef4444', textAlign: 'center' }}>
            <h4 style={{ color: '#ef4444', margin: '0 0 10px 0' }}>Danger Zone</h4>
            <p style={{ fontSize: '12px', color: '#64748b', marginBottom: '15px' }}>This will permanently erase all tests, assignments, and holidays. User accounts will remain untouched.</p>
            <button className="btn-danger" onClick={handleWipeSystem}>
              WIPE BOARD DATA
            </button>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '30px', paddingTop: '20px', borderTop: '1px solid #e2e8f0' }}>
          <button className="btn-secondary" onClick={onClose}>Close Reports</button>
        </div>
      </div>
    </div>
  );
};

export default SystemReportsModal;
