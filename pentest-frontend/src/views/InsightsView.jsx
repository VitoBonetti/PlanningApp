import React, { useState } from 'react';

// --- VISUALIZATION COMPONENTS ---
const DualBar = ({ label, actual, target, done, color, goalPct }) => {
  const maxVal = Math.max(actual, target);
  const targetPct = (target / maxVal) * 100;
  const actualPct = (actual / maxVal) * 100;
  const donePct = (done / maxVal) * 100;
  const overDelivered = actual > target;

  return (
    <div style={{ marginBottom: '14px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', marginBottom: '4px' }}>
        <span style={{ fontWeight: 'bold', color: '#475569' }}>{label}</span>
        <span style={{ fontWeight: 'bold', color: overDelivered ? color : '#64748b' }}>
          {done} Done / {actual} Forecast / {target} Goal {overDelivered && '🔥'}
        </span>
      </div>
      <div style={{ position: 'relative', height: '18px', backgroundColor: '#f8fafc', borderRadius: '4px', overflow: 'hidden', border: '1px solid #e2e8f0' }}>
        <div style={{ position: 'absolute', top: 0, left: 0, height: '100%', width: `${targetPct}%`, backgroundColor: '#e2e8f0', borderRight: '1px dashed #94a3b8' }} />
        {goalPct && <div style={{ position: 'absolute', top: 0, left: `${targetPct * goalPct}%`, height: '100%', borderLeft: '2px dashed #0f172a', zIndex: 3 }} title="95% Goal Line" />}
        <div style={{ position: 'absolute', top: '4px', left: 0, height: '10px', width: `${actualPct}%`, backgroundColor: color, borderRadius: '0 2px 2px 0', opacity: 0.3, zIndex: 1 }} />
        <div style={{ position: 'absolute', top: '4px', left: 0, height: '10px', width: `${donePct}%`, backgroundColor: color, borderRadius: '0 2px 2px 0', zIndex: 2, transition: 'width 0.5s ease' }} />
      </div>
    </div>
  );
};

const BlackBoxBar = ({ actual, done, max, min, ideal }) => {
  const maxVal = Math.max(actual, max);
  const maxPct = (max / maxVal) * 100;
  const actualPct = (actual / maxVal) * 100;
  const donePct = (done / maxVal) * 100;
  const minPct = (min / maxVal) * 100;
  const idealPct = (ideal / maxVal) * 100;
  const overDelivered = actual > max;

  return (
    <div style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
        <span style={{ fontWeight: 'bold', color: '#334155' }}>Black Box Forecast</span>
        <span style={{ fontWeight: 'bold', color: overDelivered ? '#10b981' : '#64748b' }}>
          {done} Done / {actual} Forecast {overDelivered && '🔥'}
        </span>
      </div>
      <div style={{ position: 'relative', height: '32px', backgroundColor: '#f1f5f9', borderRadius: '4px', overflow: 'hidden', border: '1px solid #e2e8f0' }}>
        <div style={{ position: 'absolute', top: 0, left: 0, height: '100%', width: `${maxPct}%`, backgroundColor: '#e2e8f0' }} />
        <div style={{ position: 'absolute', top: 0, left: `${minPct}%`, height: '100%', borderLeft: '2px dashed #ef4444', zIndex: 3 }} />
        <div style={{ position: 'absolute', top: 0, left: `${idealPct}%`, height: '100%', borderLeft: '2px dashed #10b981', zIndex: 3 }} />
        <div style={{ position: 'absolute', top: 0, left: `${maxPct}%`, height: '100%', borderLeft: '2px dashed #64748b', zIndex: 3 }} />
        <div style={{ position: 'absolute', top: '6px', left: 0, height: '20px', width: `${actualPct}%`, backgroundColor: '#475569', borderRadius: '0 4px 4px 0', opacity: 0.4, transition: 'width 0.5s ease', zIndex: 1 }} />
        <div style={{ position: 'absolute', top: '6px', left: 0, height: '20px', width: `${donePct}%`, backgroundColor: '#0f172a', borderRadius: '0 4px 4px 0', transition: 'width 0.5s ease', zIndex: 2 }} />
      </div>
      <div style={{ position: 'relative', height: '20px', marginTop: '4px' }}>
        <div style={{ position: 'absolute', left: `${minPct}%`, transform: 'translateX(-50%)', fontSize: '10px', fontWeight: 'bold', color: '#ef4444' }}>({min})</div>
        <div style={{ position: 'absolute', left: `${idealPct}%`, transform: 'translateX(-50%)', fontSize: '10px', fontWeight: 'bold', color: '#10b981' }}>({ideal})</div>
        <div style={{ position: 'absolute', left: `${maxPct}%`, transform: 'translateX(-50%)', fontSize: '10px', fontWeight: 'bold', color: '#64748b' }}>({max})</div>
      </div>
    </div>
  );
};

const BreakdownPills = ({ stats }) => (
  <div style={{ display: 'flex', gap: '16px', marginTop: '12px' }}>
    <div style={{ flex: 1, backgroundColor: '#f8fafc', padding: '12px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
      <div style={{ fontSize: '10px', fontWeight: 'bold', color: '#64748b', textTransform: 'uppercase', marginBottom: '8px' }}>Business Criticality (Forecast)</div>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <span style={{ backgroundColor: '#fee2e2', color: '#b91c1c', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 'bold' }}>Critical: {stats.critical}</span>
        <span style={{ backgroundColor: '#f1f5f9', color: '#475569', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 'bold' }}>Non-Critical: {stats.nonCritical}</span>
      </div>
    </div>
    <div style={{ flex: 1, backgroundColor: '#f8fafc', padding: '12px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
      <div style={{ fontSize: '10px', fontWeight: 'bold', color: '#64748b', textTransform: 'uppercase', marginBottom: '8px' }}>KPI Status (Forecast)</div>
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        <span style={{ backgroundColor: '#dcfce3', color: '#166534', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 'bold' }}>KPI: {stats.kpi}</span>
        <span style={{ backgroundColor: '#f1f5f9', color: '#475569', padding: '4px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 'bold' }}>Non-KPI: {stats.nonKpi}</span>
      </div>
    </div>
  </div>
);

const CapacityTrendChart = ({ yearlyData, targetYearStr, grossCapacity }) => {
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const maxVal = grossCapacity > 0 ? grossCapacity * 1.15 : 10; // Fallback to avoid dividing by 0

  const makePath = (data) => {
    if (!data || data.length === 0) return '';
    return data.map((v, i) => `${(i / 11) * 100},${100 - (v / maxVal) * 100}`).join(' L ');
  };

  // Sort years so oldest render first (in the back)
  const allYears = Object.keys(yearlyData || {}).sort((a, b) => parseInt(a) - parseInt(b));
  const historicalYears = allYears.filter(y => y !== targetYearStr);
  const targetData = yearlyData ? yearlyData[targetYearStr] : [];

  return (
    <div style={{ backgroundColor: 'white', padding: '32px', borderRadius: '12px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
        <div>
          <h3 style={{ margin: '0 0 8px 0', color: '#0f172a', fontSize: '18px' }}>Holiday Consumption Heatmap</h3>
          <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
            <span style={{ color: '#0f172a', fontSize: '13px', display: 'flex', alignItems: 'center', fontWeight: 'bold' }}>
              <span style={{ display: 'inline-block', width: '10px', height: '10px', backgroundColor: '#ef4444', borderRadius: '50%', marginRight: '6px' }}></span>
              {targetYearStr}
            </span>
            {historicalYears.length > 0 && (
              <span style={{ color: '#64748b', fontSize: '13px', display: 'flex', alignItems: 'center' }}>
                <span style={{ display: 'inline-block', width: '10px', height: '10px', backgroundColor: 'rgba(239, 68, 68, 0.4)', borderRadius: '50%', marginRight: '6px' }}></span>
                Historical Volume
              </span>
            )}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '11px', fontWeight: 'bold', color: '#64748b', textTransform: 'uppercase' }}>Avg Monthly Capacity</div>
          <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#0f172a' }}>{grossCapacity.toFixed(1)} <span style={{ fontSize: '14px', color: '#94a3b8' }}>cr/mo</span></div>
        </div>
      </div>

      <div style={{ position: 'relative', height: '280px', width: '100%', marginTop: '30px', borderBottom: '1px solid #cbd5e1' }}>
        
        {/* Y-Axis Guidelines */}
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', pointerEvents: 'none', zIndex: 0 }}>
          {[100, 75, 50, 25, 0].map(pct => (
            <div key={pct} style={{ width: '100%', borderTop: '1px dashed #e2e8f0', position: 'relative' }}>
              <span style={{ position: 'absolute', top: '-8px', left: '-30px', fontSize: '10px', color: '#94a3b8' }}>{((maxVal * (pct / 100))).toFixed(0)}</span>
            </div>
          ))}
        </div>

        {/* SVG Drawing Area */}
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ width: '100%', height: '100%', overflow: 'visible', position: 'relative', zIndex: 1 }}>
          <defs>
            <linearGradient id="heatmapGradient" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="rgba(239, 68, 68, 0.25)" />
              <stop offset="100%" stopColor="rgba(239, 68, 68, 0.0)" />
            </linearGradient>
            <linearGradient id="currentGradient" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="rgba(239, 68, 68, 0.5)" />
              <stop offset="100%" stopColor="rgba(239, 68, 68, 0.0)" />
            </linearGradient>
          </defs>

          {/* BACKGROUND LAYERS: mix-blend-mode: multiply creates the heatmap intensity */}
          {historicalYears.map(year => {
            const pathData = makePath(yearlyData[year]);
            if (!pathData) return null;
            return (
              <g key={year} style={{ mixBlendMode: 'multiply' }}>
                 <path d={`M 0,100 L ${pathData} L 100,100 Z`} fill="url(#heatmapGradient)" />
                 <path d={`M ${pathData}`} fill="none" stroke="rgba(239, 68, 68, 0.4)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
              </g>
            );
          })}

          {/* FRONT LAYER: Current Year */}
          {targetData && targetData.length > 0 && (
             <g style={{ mixBlendMode: 'multiply' }}>
                <path d={`M 0,100 L ${makePath(targetData)} L 100,100 Z`} fill="url(#currentGradient)" />
                <path d={`M ${makePath(targetData)}`} fill="none" stroke="#ef4444" strokeWidth="2.5" vectorEffect="non-scaling-stroke" />
             </g>
          )}
        </svg>

        {/* X-Axis Labels */}
        <div style={{ display: 'flex', justifyContent: 'space-between', position: 'absolute', bottom: '-24px', left: 0, right: 0 }}>
          {months.map((m, i) => (
            <span key={m} style={{ fontSize: '11px', color: '#64748b', fontWeight: '500', transform: i === 0 ? 'translateX(-50%)' : i === 11 ? 'translateX(50%)' : 'none' }}>
              {m}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};

const InsightsView = ({ currentUser, setCurrentView, boardData, availableAssets,  handleWipeSystem }) => {
  const [activeTab, setActiveTab] = useState('targets');

  if (!boardData) return null;

  // --- CORE MATH & UTILS ---
  const getWorkingDays = (startDate, endDate) => {
    if (!startDate || !endDate) return 0;
    const start = new Date(startDate + 'T00:00:00');
    const end = new Date(endDate + 'T00:00:00');
    let count = 0;
    let current = new Date(start);
    while (current <= end) {
      const dayOfWeek = current.getDay();
      if (dayOfWeek !== 0 && dayOfWeek !== 6) count++;
      current.setDate(current.getDate() + 1);
    }
    return count;
  };

  const isInternalService = (serviceId) => {
    const s = boardData.services.find(srv => srv.id === serviceId);
    return s && !s.name.toLowerCase().includes('black');
  };

  const activePentesters = boardData.pentesters.filter(p => p.role !== 'read_only');
  const currentYearStr = String(boardData.year);

  // --- TREND BUCKET MATH ---

  // const totalBaseCapacity = activePentesters.reduce((sum, p) => {
  //   const startWeek = p.start_week || 1;
  //   const activeWeeks = Math.max(0, 52 - startWeek + 1);
  //   const cap = p.capacity ?? p.base_capacity ?? 1.0; // Properly respects 0
  //   return sum + (cap * activeWeeks);
  // }, 0);

  const targetYear = parseInt(currentYearStr);

  const totalBaseCapacity = activePentesters.reduce((sum, p) => {
    const sw = p.start_week || 1;
    const sy = p.start_year || 2024; // Fallback to 2024 for older accounts
    const ew = p.end_week;
    const ey = p.end_year;
    const cap = p.capacity ?? p.base_capacity ?? 1.0;

    let activeWeeks = 0;

    if (targetYear < sy) {
      // 1. Hasn't started yet
      activeWeeks = 0; 
    } else if (ey && targetYear > ey) {
      // 2. Already left in a previous year
      activeWeeks = 0; 
    } else if (targetYear === sy && targetYear === ey) {
      // 3. Started and left in the exact same year
      activeWeeks = ew - sw + 1; 
    } else if (targetYear === sy) {
      // 4. Started this year, hasn't left yet
      activeWeeks = 52 - sw + 1; 
    } else if (targetYear === ey) {
      // 5. Started previously, but left during this year
      activeWeeks = ew; 
    } else {
      // 6. Employed the entire year
      activeWeeks = 52; 
    }

    // Ensure we don't return negative weeks somehow, and multiply by capacity
    return sum + (cap * Math.max(0, activeWeeks));
  }, 0);

  const calculateMonthlyTrend = () => {
    const yearlyLoss = {}; 
    yearlyLoss[currentYearStr] = Array(12).fill(0);

    boardData.events.forEach(e => {
      if (!e.start || !e.end) return;

      const start = new Date(e.start + 'T00:00:00');
      const end = new Date(e.end + 'T00:00:00');

      let dailyDeduction = 0;
      if (e.type === 'personal_holiday') {
        const p = activePentesters.find(user => user.id === e.user_id);
        if (p) dailyDeduction = (p.capacity ?? p.base_capacity ?? 1.0) / 5;
      } else if (e.type === 'team_day') {
        dailyDeduction = activePentesters.reduce((acc, p) => acc + ((p.capacity ?? p.base_capacity ?? 1.0) / 5), 0);
      } else if (e.type === 'national_holiday') {
        const affected = activePentesters.filter(p => e.location === 'Global' || p.location === e.location);
        dailyDeduction = affected.reduce((acc, p) => acc + ((p.capacity ?? p.base_capacity ?? 1.0) / 5), 0);
      }

      if (dailyDeduction === 0) return;

      let current = new Date(start);
      while (current <= end) {
        const yearStr = String(current.getFullYear());
        
        if (!yearlyLoss[yearStr]) {
           yearlyLoss[yearStr] = Array(12).fill(0);
        }

        const dayOfWeek = current.getDay();
        if (dayOfWeek !== 0 && dayOfWeek !== 6) { // Only count Mon-Fri
          yearlyLoss[yearStr][current.getMonth()] += dailyDeduction;
        }
        current.setDate(current.getDate() + 1);
      }
    });

    // --- PRECISE GROSS CAPACITY MATH ---
    const targetYearNum = parseInt(currentYearStr);
    let totalWeeksCapacityInYear = 0;

    activePentesters.forEach(p => {
      const sw = p.start_week || 1;
      const sy = p.start_year || 2024;
      const ew = p.end_week;
      const ey = p.end_year;
      const cap = p.capacity ?? p.base_capacity ?? 1.0;

      let activeWeeks = 0;
      if (targetYearNum < sy) activeWeeks = 0; // Not hired yet
      else if (ey && targetYearNum > ey) activeWeeks = 0; // Already left
      else if (targetYearNum === sy && targetYearNum === ey) activeWeeks = (ew - sw) + 1; // Joined and left this year
      else if (targetYearNum === sy) activeWeeks = 52 - sw + 1; // Joined this year
      else if (targetYearNum === ey) activeWeeks = ew; // Left this year
      else activeWeeks = 52; // Worked the full year

      totalWeeksCapacityInYear += (Math.max(0, activeWeeks) * cap);
    });

    const preciseAverageMonthlyCapacity = totalWeeksCapacityInYear / 12;

    return {
      yearlyData: yearlyLoss,
      gross: preciseAverageMonthlyCapacity
    };
  };

  const trendData = calculateMonthlyTrend();

  const getEventCreditLoss = (e, targetYear) => {
    if (!e.start || !e.end || (!e.start.startsWith(targetYear) && !e.end.startsWith(targetYear))) return 0;
    const daysOff = getWorkingDays(e.start, e.end);
    if (daysOff === 0) return 0;

    let dailyDeduction = 0;
    if (e.type === 'personal_holiday') {
      const p = activePentesters.find(user => user.id === e.user_id);
      if (p) dailyDeduction = (p.capacity ?? p.base_capacity ?? 1.0) / 5;
    } else if (e.type === 'team_day') {
      dailyDeduction = activePentesters.reduce((acc, p) => acc + ((p.capacity ?? p.base_capacity ?? 1.0) / 5), 0);
    } else if (e.type === 'national_holiday') {
      const affected = activePentesters.filter(p => e.location === 'Global' || p.location === e.location);
      dailyDeduction = affected.reduce((acc, p) => acc + ((p.capacity ?? p.base_capacity ?? 1.0) / 5), 0);
    }
    return daysOff * dailyDeduction;
  };

  const totalPTOLoss = boardData.events.reduce((sum, e) => sum + getEventCreditLoss(e, currentYearStr), 0);
  const netCapacity = totalBaseCapacity - totalPTOLoss;

  let assignedWhiteBox = 0, assignedAdversary = 0, assignedProjects = 0;
  boardData.assignments.forEach(a => {
    const test = boardData.scheduled.find(t => t.id === a.test_id);
    if (test && isInternalService(test.service_id)) {
      const sName = boardData.services.find(srv => srv.id === test.service_id).name.toLowerCase();
      if (sName.includes('white')) assignedWhiteBox += a.allocated_credits;
      else if (sName.includes('adversary')) assignedAdversary += a.allocated_credits;
      else assignedProjects += a.allocated_credits;
    }
  });

  const totalAllocated = assignedWhiteBox + assignedAdversary + assignedProjects;
  const benchTime = Math.max(0, netCapacity - totalAllocated);

  const scheduledTests = boardData.scheduled.filter(t => isInternalService(t.service_id));
  const backlogTests = boardData.backlog.filter(t => isInternalService(t.service_id));
  const unassignedAssets = (availableAssets || []).filter(a => !a.is_assigned && !String(a.gost_service || '').toLowerCase().includes('black'));

  const getDemandBreakdown = (tests) => {
    const bd = { white: 0, adv: 0, proj: 0 };
    tests.forEach(t => {
      const sName = boardData.services.find(srv => srv.id === t.service_id)?.name.toLowerCase() || '';
      const demand = t.credits * t.duration;
      if (sName.includes('white')) bd.white += demand;
      else if (sName.includes('adversary')) bd.adv += demand;
      else bd.proj += demand;
    });
    return bd;
  };

  const schedBD = getDemandBreakdown(scheduledTests);
  const backlogBD = getDemandBreakdown(backlogTests);
  const assetBD = { white: 0, adv: 0, proj: 0 };
  unassignedAssets.forEach(a => {
    const gost = String(a.gost_service || '').toLowerCase();
    if (gost.includes('white')) assetBD.white += 2.0;
    else if (gost.includes('adversary')) assetBD.adv += 2.0;
    else assetBD.proj += 2.0;
  });

  const scheduledDemand = scheduledTests.reduce((acc, t) => acc + (t.credits * t.duration), 0);
  const backlogDemand = backlogTests.reduce((acc, t) => acc + (t.credits * t.duration), 0);
  const assetDemand = unassignedAssets.length * 2.0;

  const totalForecastedDemand = scheduledDemand + backlogDemand + assetDemand;
  const capacityGap = netCapacity - totalForecastedDemand;

  const getStats = (serviceKeyword) => {
    const matchingTests = [...boardData.scheduled, ...boardData.backlog].filter(t => {
      const sName = boardData.services.find(s => s.id === t.service_id)?.name.toLowerCase() || '';
      return sName.includes(serviceKeyword);
    });

    const matchingAssets = (availableAssets || []).filter(a =>
      String(a.gost_service || '').toLowerCase().includes(serviceKeyword)
    );

    let categories = {
      'Crown Jewels': { f: 0, d: 0 },
      'X-One Global': { f: 0, d: 0 },
      'AI': { f: 0, d: 0 },
      'GIS': { f: 0, d: 0 },
      'Market Jewels': { f: 0, d: 0 },
      'Digital': { f: 0, d: 0 },
      'Mobile': { f: 0, d: 0 },
      'Uncategorized': { f: 0, d: 0 }
    };

    if (serviceKeyword === 'white') {
      matchingAssets.filter(a => !a.is_assigned).forEach(a => {
        const cat = a.whitebox_category || 'Uncategorized';
        if (categories[cat]) categories[cat].f++;
        else categories['Uncategorized'].f++;
      });
      matchingTests.forEach(t => {
        const cat = t.whitebox_category || 'Uncategorized';
        if (categories[cat]) {
          categories[cat].f++;
          if (t.status === 'Completed') categories[cat].d++;
        } else {
          categories['Uncategorized'].f++;
          if (t.status === 'Completed') categories['Uncategorized'].d++;
        }
      });
    }

    let assetCrit = 0, assetNonCrit = 0, assetKpi = 0, assetNonKpi = 0;
    matchingAssets.forEach(a => {
      if (['8', '9'].includes(String(a.business_critical))) assetCrit++; else assetNonCrit++;
      if (String(a.kpi).toLowerCase() === 'yes') assetKpi++; else assetNonKpi++;
    });

    const assignedAssetsCount = matchingAssets.filter(a => a.is_assigned).length;
    const manualCount = Math.max(0, matchingTests.length - assignedAssetsCount);
    const forecastTotal = matchingAssets.length + manualCount;
    const completedTests = matchingTests.filter(t => t.status === 'Completed').length;

    return {
      forecastTotal,
      completed: completedTests,
      categories,
      critical: assetCrit,
      nonCritical: assetNonCrit + manualCount,
      kpi: assetKpi,
      nonKpi: assetNonKpi + manualCount,
    };
  };

  const bbStats = getStats('black');
  const wbStats = getStats('white');
  const advStats = getStats('adversary');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 65px)', backgroundColor: '#f8fafc', fontFamily: 'system-ui, sans-serif', fontSize: '13px', color: '#334155' }}>
      <div style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1400px', margin: '0 auto', width: '100%', boxSizing: 'border-box' }}>
          {currentUser?.role !== 'pentester' && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
                <div style={{ backgroundColor: 'white', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0', borderTop: '4px solid #64748b', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                  <span style={{ color: '#64748b', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>1. Gross Capacity</span>
                  <div style={{ fontSize: '1.8rem', fontWeight: 'bold', color: '#0f172a', marginTop: '4px' }}>{totalBaseCapacity.toFixed(1)} <span style={{fontSize:'1rem', color:'#94a3b8', fontWeight:'normal'}}>cr</span></div>
                </div>
                <div style={{ backgroundColor: 'white', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0', borderTop: '4px solid #ef4444', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                  <span style={{ color: '#64748b', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>2. PTO & Holidays</span>
                  <div style={{ fontSize: '1.8rem', fontWeight: 'bold', color: '#ef4444', marginTop: '4px' }}>-{totalPTOLoss.toFixed(1)} <span style={{fontSize:'1rem', color:'#fca5a5', fontWeight:'normal'}}>cr</span></div>
                </div>
                <div style={{ backgroundColor: 'white', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0', borderTop: '4px solid #3b82f6', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                  <span style={{ color: '#64748b', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>3. White Box (Assigned)</span>
                  <div style={{ fontSize: '1.8rem', fontWeight: 'bold', color: '#3b82f6', marginTop: '4px' }}>-{assignedWhiteBox.toFixed(1)} <span style={{fontSize:'1rem', color:'#93c5fd', fontWeight:'normal'}}>cr</span></div>
                </div>
                <div style={{ backgroundColor: 'white', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0', borderTop: '4px solid #f97316', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                  <span style={{ color: '#64748b', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>4. Adversary (Assigned)</span>
                  <div style={{ fontSize: '1.8rem', fontWeight: 'bold', color: '#f97316', marginTop: '4px' }}>-{assignedAdversary.toFixed(1)} <span style={{fontSize:'1rem', color:'#fdba74', fontWeight:'normal'}}>cr</span></div>
                </div>
                <div style={{ backgroundColor: 'white', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0', borderTop: '4px solid #8b5cf6', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                  <span style={{ color: '#64748b', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>5. Projects (Assigned)</span>
                  <div style={{ fontSize: '1.8rem', fontWeight: 'bold', color: '#8b5cf6', marginTop: '4px' }}>-{assignedProjects.toFixed(1)} <span style={{fontSize:'1rem', color:'#c4b5fd', fontWeight:'normal'}}>cr</span></div>
                </div>
                <div style={{ backgroundColor: 'white', padding: '16px', borderRadius: '8px', border: '1px solid #e2e8f0', borderTop: '4px solid #10b981', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                  <span style={{ color: '#64748b', fontWeight: '600', fontSize: '11px', textTransform: 'uppercase' }}>= Unassigned Bench</span>
                  <div style={{ fontSize: '1.8rem', fontWeight: 'bold', color: '#10b981', marginTop: '4px' }}>{benchTime.toFixed(1)} <span style={{fontSize:'1rem', color:'#6ee7b7', fontWeight:'normal'}}>cr</span></div>
                </div>
              </div>
    
              <div style={{ backgroundColor: capacityGap < 0 ? '#fef2f2' : '#f0fdf4', padding: '24px', borderRadius: '8px', border: `1px solid ${capacityGap < 0 ? '#fecaca' : '#bbf7d0'}`, boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                <h3 style={{ margin: '0 0 16px 0', color: capacityGap < 0 ? '#991b1b' : '#166534', fontSize: '1.2rem' }}>Annual Workload Forecast</h3>
    
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '24px', borderBottom: `2px solid ${capacityGap < 0 ? '#fca5a5' : '#86efac'}`, paddingBottom: '20px', marginBottom: '20px' }}>
                  <div style={{ backgroundColor: 'white', padding: '16px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}><span style={{ fontWeight: '600', color: '#334155' }}>Scheduled Tests</span><span style={{ fontWeight: 'bold', color: '#0f172a' }}>{scheduledDemand.toFixed(1)} cr</span></div>
                    <details><summary style={{ fontSize: '12px', color: '#64748b', cursor: 'pointer', outline: 'none' }}>View Breakdown</summary><div style={{ padding: '8px', marginTop: '4px', backgroundColor: '#f8fafc', borderRadius: '4px', fontSize: '12px', color: '#475569' }}><div style={{ display: 'flex', justifyContent: 'space-between' }}><span>White Box:</span> <strong>{schedBD.white.toFixed(1)}</strong></div><div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Adversary:</span> <strong>{schedBD.adv.toFixed(1)}</strong></div><div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Projects:</span> <strong>{schedBD.proj.toFixed(1)}</strong></div></div></details>
                  </div>
                  <div style={{ backgroundColor: 'white', padding: '16px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}><span style={{ fontWeight: '600', color: '#334155' }}>Backlog Tests</span><span style={{ fontWeight: 'bold', color: '#0f172a' }}>{backlogDemand.toFixed(1)} cr</span></div>
                    <details><summary style={{ fontSize: '12px', color: '#64748b', cursor: 'pointer', outline: 'none' }}>View Breakdown</summary><div style={{ padding: '8px', marginTop: '4px', backgroundColor: '#f8fafc', borderRadius: '4px', fontSize: '12px', color: '#475569' }}><div style={{ display: 'flex', justifyContent: 'space-between' }}><span>White Box:</span> <strong>{backlogBD.white.toFixed(1)}</strong></div><div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Adversary:</span> <strong>{backlogBD.adv.toFixed(1)}</strong></div><div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Projects:</span> <strong>{backlogBD.proj.toFixed(1)}</strong></div></div></details>
                  </div>
                  <div style={{ backgroundColor: 'white', padding: '16px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}><span style={{ fontWeight: '600', color: '#334155' }}>Unassigned Assets ({unassignedAssets.length})</span><span style={{ fontWeight: 'bold', color: '#0f172a' }}>{assetDemand.toFixed(1)} cr</span></div>
                    <details><summary style={{ fontSize: '12px', color: '#64748b', cursor: 'pointer', outline: 'none' }}>View Gost Breakdown</summary><div style={{ padding: '8px', marginTop: '4px', backgroundColor: '#f8fafc', borderRadius: '4px', fontSize: '12px', color: '#475569' }}><div style={{ display: 'flex', justifyContent: 'space-between' }}><span>White Box:</span> <strong>{assetBD.white.toFixed(1)}</strong></div><div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Adversary:</span> <strong>{assetBD.adv.toFixed(1)}</strong></div><div style={{ display: 'flex', justifyContent: 'space-between' }}><span>Unknown/Projects:</span> <strong>{assetBD.proj.toFixed(1)}</strong></div></div></details>
                  </div>
                </div>
    
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: '12px', fontWeight: 'bold', color: capacityGap < 0 ? '#7f1d1d' : '#14532d', textTransform: 'uppercase', marginBottom: '4px' }}>Net Capacity Remaining</div>
                    <div style={{ fontSize: '2rem', fontWeight: 'bold', color: capacityGap < 0 ? '#dc2626' : '#16a34a', lineHeight: '1' }}>{capacityGap > 0 ? '+' : ''}{capacityGap.toFixed(1)} <span style={{fontSize:'1.2rem', color: capacityGap < 0 ? '#fca5a5' : '#86efac', fontWeight: 'normal'}}>cr</span></div>
                  </div>
                  <div style={{ textAlign: 'right', color: capacityGap < 0 ? '#dc2626' : '#16a34a', fontWeight: '600', fontSize: '14px', backgroundColor: 'white', padding: '12px 24px', borderRadius: '6px', border: `1px solid ${capacityGap < 0 ? '#fecaca' : '#bbf7d0'}` }}>
                    {capacityGap < 0 ? `⚠️ You are understaffed by ${Math.abs(capacityGap).toFixed(1)} credits for this workload.` : "✅ You have enough capacity to complete the pool."}
                  </div>
                </div>
              </div>
            </>
          )}

          <div style={{ backgroundColor: 'white', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.05)', display: 'block', minHeight: '400px', marginBottom: '40px' }}>

            <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', backgroundColor: '#f8fafc', padding: '0 16px', borderRadius: '8px 8px 0 0' }}>
              {currentUser?.role !== 'pentester' && (
                <>
                  <button onClick={() => setActiveTab('targets')} style={{ padding: '16px 24px', border: 'none', background: 'none', cursor: 'pointer', fontWeight: 'bold', color: activeTab === 'targets' ? '#f59e0b' : '#64748b', borderBottom: activeTab === 'targets' ? '2px solid #f59e0b' : '2px solid transparent' }}>Objectives & Targets</button>
                  <button onClick={() => setActiveTab('holiday_insight')} style={{ padding: '16px 24px', border: 'none', background: 'none', cursor: 'pointer', fontWeight: 'bold', color: activeTab === 'holiday_insight' ? '#2563eb' : '#64748b', borderBottom: activeTab === 'holiday_insight' ? '2px solid #2563eb' : '2px solid transparent' }}>Holidays Insight</button>
                </>
              )}
            </div>

            <div style={{ padding: '32px' }}>
              {activeTab === 'targets' && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '60px', maxWidth: '1200px' }}>

                  <div style={{ paddingBottom: '32px', borderBottom: '1px solid #e2e8f0' }}>
                    <h2 style={{ marginTop: 0, color: '#0f172a' }}>Adversary Simulation</h2>
                    <p style={{ fontSize: '13px', color: '#64748b', margin: '4px 0 16px 0' }}>Goal: Ensure 95% of priority apps are simulated.</p>
                    <DualBar label="Adversary Completed Apps" done={advStats.completed} actual={advStats.completed} target={37} color="#f97316" goalPct={0.95} />
                  </div>
                  <div style={{ paddingBottom: '32px', borderBottom: '1px solid #e2e8f0' }}>
                    <h2 style={{ marginTop: 0, color: '#0f172a' }}>Vendor Black Box Forecast</h2>
                    <p style={{ fontSize: '13px', color: '#64748b', margin: '4px 0 16px 0' }}>Forecast = Assets in Pool + Custom Projects.</p>
                    <BlackBoxBar
                      done={bbStats.completed}
                      actual={bbStats.forecastTotal}
                      max={140} min={100} ideal={120}
                    />
                    <BreakdownPills stats={bbStats} />
                  </div>

                  <div>
                    <h2 style={{ marginTop: 0, color: '#0f172a' }}>White Box Applications</h2>
                    <p style={{ fontSize: '13px', color: '#64748b', margin: '4px 0 16px 0' }}>Forecast = Assets in Pool + Custom Projects.</p>
                    <DualBar
                      label="Total White Box Forecast"
                      done={wbStats.completed}
                      actual={wbStats.forecastTotal}
                      target={110}
                      color="#3b82f6"
                    />
                    <BreakdownPills stats={wbStats} />

                    <div style={{ marginTop: '32px', backgroundColor: '#f8fafc', padding: '24px', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                      <h4 style={{ margin: '0 0 20px 0', color: '#0f172a' }}>Subcategory Forecast Breakdown</h4>

                      {boardData.whitebox_categories?.map((cat) => {
                        const stats = wbStats.categories[cat.name] || { f: 0, d: 0 };
                        return (
                          <DualBar
                            key={cat.id}
                            label={cat.name}
                            done={stats.d}
                            actual={stats.f}
                            target={cat.target_goal}
                            color="#3b82f6"
                          />
                        );
                      })}

                      {wbStats.categories['Uncategorized']?.f > 0 && (
                        <div style={{ fontSize: '12px', color: '#b45309', fontWeight: 'bold', marginTop: '16px', backgroundColor: '#fef3c7', padding: '8px', borderRadius: '4px', textAlign: 'center' }}>
                          + {wbStats.categories['Uncategorized'].f} Uncategorized Tests in Forecast
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

            {activeTab === 'holiday_insight' && (
                <div style={{ maxWidth: '1000px', marginLeft: '30px' }}>
                 <CapacityTrendChart 
                    yearlyData={trendData.yearlyData} 
                    targetYearStr={currentYearStr} 
                    grossCapacity={trendData.gross} 
                  />
                  
                  <div style={{ marginTop: '40px', padding: '20px', backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                    <h4 style={{ margin: '0 0 8px 0', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>
                      Predictive Planning Strategy
                    </h4>
                    <p style={{ margin: 0, color: '#475569', fontSize: '13px', lineHeight: '1.6' }}>
                      This chart displays the <strong>Holiday Consumption Trend</strong> for each month. The red area represents the total capacity <em>lost</em> to booked personal time off, team days, and national holidays. 
                      Compare it against the dashed historical trendline to anticipate seasonal spikes in absences (like August and December). Use this insight to avoid scheduling heavy White Box and Adversary simulations during these high-PTO months.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InsightsView;
