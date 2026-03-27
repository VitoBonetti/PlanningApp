import React from 'react';

const modalBackdropStyle = { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(15, 23, 42, 0.4)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, animation: 'fadeIn 0.2s ease-out' };
const modalContentStyle = { backgroundColor: 'white', padding: '32px', borderRadius: '12px', color: '#334155', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)', animation: 'slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1)', border: '1px solid #e2e8f0' };
const closeButtonStyle = { backgroundColor: '#e2e8f0', color: '#333', border: 'none', padding: '10px 20px', borderRadius: '4px', cursor: 'pointer' };

const TestDirectoryModal = ({
  showTestDirectory,
  setShowTestDirectory,
  setCurrentView,
  setNewTest,
  setShowTestForm,
  directoryFilter,
  setDirectoryFilter,
  boardData,
  openEditModal,
  handleDeleteTest
}) => {
  if (!showTestDirectory || !boardData) return null;

  return (
    <div style={modalBackdropStyle}>
      <div style={{...modalContentStyle, width: '900px', maxHeight: '85vh', display: 'flex', flexDirection: 'column'}}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
          <h2 style={{ margin: 0, color: '#0f172a' }}>Test & Project Directory</h2>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn-primary" onClick={() => { setShowTestDirectory(false); setCurrentView('assets'); }}>+ Test from Assets</button>
            <button className="btn-secondary" onClick={() => { setShowTestDirectory(false); setNewTest({ name: '', service_id: '', type: 'project', credits_per_week: 1.0, duration_weeks: 1, asset_ids: [] }); setShowTestForm(true); }}>+ Custom Project</button>
            <button className="btn-danger" onClick={() => setShowTestDirectory(false)}>Close</button>
          </div>
        </div>

        {/* Toggle */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '15px', paddingBottom: '15px', borderBottom: '1px solid #e2e8f0' }}>
          {['Not Planned', 'Planned', 'Completed'].map(status => (
            <button key={status} onClick={() => setDirectoryFilter(status)} style={{ padding: '6px 16px', borderRadius: '4px', border: 'none', cursor: 'pointer', fontWeight: '600', fontSize: '12px', backgroundColor: directoryFilter === status ? '#e2e8f0' : 'transparent', color: directoryFilter === status ? '#0f172a' : '#64748b' }}>
              {status}
            </button>
          ))}
        </div>

        {/* Aligned Table with Team Column */}
        <div style={{ overflowY: 'auto', flex: 1 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead style={{ position: 'sticky', top: 0, zIndex: 5, backgroundColor: '#f8fafc' }}>
              <tr style={{ borderBottom: '2px solid #cbd5e1' }}>
                <th style={{ padding: '10px', textAlign: 'left', fontWeight: '600', color: '#475569' }}>Name</th>
                <th style={{ padding: '10px', textAlign: 'left', fontWeight: '600', color: '#475569' }}>Service</th>
                <th style={{ padding: '10px', textAlign: 'left', fontWeight: '600', color: '#475569' }}>Load</th>
                <th style={{ padding: '10px', textAlign: 'left', fontWeight: '600', color: '#475569' }}>Timing</th>
                <th style={{ padding: '10px', textAlign: 'left', fontWeight: '600', color: '#475569' }}>Team Assigned</th>
                <th style={{ padding: '10px', textAlign: 'right', fontWeight: '600', color: '#475569' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {[...boardData.backlog, ...boardData.scheduled]
                .filter(t => (t.status || 'Not Planned') === directoryFilter)
                .map(t => {
                const service = boardData.services.find(s => s.id === t.service_id);
                const testAssignments = boardData.assignments.filter(a => a.test_id === t.id);
                const assignedNames = [...new Set(testAssignments.map(a => a.user_name.split(' ')[0]))].join(', ');

                return (
                  <tr key={t.id} style={{ borderBottom: '1px solid #e2e8f0' }}>
                    <td style={{ padding: '10px', textAlign: 'left', fontWeight: '600', color: '#0f172a' }}>{t.name}</td>
                    <td style={{ padding: '10px', textAlign: 'left', color: '#334155' }}>{service?.name}</td>
                    <td style={{ padding: '10px', textAlign: 'left', color: '#64748b' }}>{t.credits} cr / {t.duration} wk</td>
                    <td style={{ padding: '10px', textAlign: 'left' }}>
                      {t.startWeek ? <span style={{ backgroundColor: '#d1fae5', color: '#059669', padding: '2px 6px', borderRadius: '4px', fontWeight: '600', fontSize: '11px' }}>Wk {t.startWeek} ({t.startYear})</span> : <span style={{ color: '#94a3b8', fontStyle: 'italic' }}>Unscheduled</span>}
                    </td>
                    <td style={{ padding: '10px', textAlign: 'left', color: '#334155', fontWeight: '500' }}>
                      {assignedNames ? assignedNames : <span style={{ color: '#94a3b8', fontStyle: 'italic', fontSize: '11px' }}>Unassigned</span>}
                    </td>
                    <td style={{ padding: '10px', textAlign: 'right' }}>
                      <button style={{ padding: '4px 8px', fontSize: '11px', backgroundColor: 'white', color: '#475569', border: '1px solid #cbd5e1', borderRadius: '4px', cursor: 'pointer', fontWeight: '600' }} onClick={() => { setShowTestDirectory(false); openEditModal(t); }}>Edit</button>
                      <button style={{ padding: '4px 8px', fontSize: '11px', backgroundColor: '#fee2e2', color: '#dc2626', border: '1px solid #fecaca', borderRadius: '4px', cursor: 'pointer', marginLeft: '8px', fontWeight: '600' }} onClick={() => handleDeleteTest(t.id)}>Delete</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default TestDirectoryModal;