import React, { useState, useEffect } from 'react';
import axios from 'axios';

const MarketView = () => {
  const [markets, setMarkets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedMarket, setSelectedMarket] = useState(null); // Tracks the active selection

  useEffect(() => {
    fetchMarkets();
  }, []);

  const fetchMarkets = async () => {
    try {
      const res = await axios.get('/api/markets/');
      const data = res.data.markets || [];
      setMarkets(data);
      // Auto-select the first market if nothing is selected yet
      if (data.length > 0 && !selectedMarket) {
        setSelectedMarket(data[0]);
      }
    } catch (err) {
      console.error("Failed to fetch markets", err);
    } finally {
      setLoading(false);
    }
  };

  const filteredMarkets = markets.filter(m => 
    (m.name || '').toLowerCase().includes(search.toLowerCase()) || 
    (m.code || '').toLowerCase().includes(search.toLowerCase()) ||
    (m.region || '').toLowerCase().includes(search.toLowerCase())
  );

  if (loading) return <div style={{ padding: '40px', color: '#64748b' }}>Loading Global Markets...</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 65px)', backgroundColor: '#f8fafc' }}>
      
      {/* STATIC TOP HEADER */}
      <div style={{ padding: '20px 32px', backgroundColor: 'white', borderBottom: '1px solid #e2e8f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 10 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '24px', color: '#0f172a' }}>Global Markets</h1>
          <p style={{ margin: '4px 0 0 0', color: '#64748b', fontSize: '14px' }}>Overview of active regions and languages.</p>
        </div>
      </div>

      {/* SPLIT SCREEN WORKSPACE */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        
        {/* LEFT PANE: SCROLLABLE LIST */}
        <div style={{ width: '380px', minWidth: '380px', backgroundColor: 'white', borderRight: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column' }}>
          
          {/* List Search Bar */}
          <div style={{ padding: '16px', borderBottom: '1px solid #e2e8f0', backgroundColor: '#f8fafc' }}>
            <input 
              type="text" 
              placeholder="🔍 Search name, code, or region..." 
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ width: '100%', padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: '6px', boxSizing: 'border-box', outline: 'none' }}
            />
          </div>

          {/* Actual List */}
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {filteredMarkets.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: '#94a3b8' }}>No markets match your search.</div>
            ) : (
              filteredMarkets.map(market => {
                const isSelected = selectedMarket?.id === market.id;
                return (
                  <div 
                    key={market.id} 
                    onClick={() => setSelectedMarket(market)}
                    style={{ 
                      padding: '16px', 
                      borderBottom: '1px solid #f1f5f9', 
                      cursor: 'pointer',
                      backgroundColor: isSelected ? '#eff6ff' : 'transparent',
                      borderLeft: isSelected ? '4px solid #3b82f6' : '4px solid transparent',
                      transition: 'background-color 0.2s ease'
                    }}
                    onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = '#f8fafc'; }}
                    onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.backgroundColor = 'transparent'; }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                      <div style={{ fontWeight: 'bold', color: isSelected ? '#1d4ed8' : '#0f172a', fontSize: '14px' }}>
                        {market.name}
                      </div>
                      <span style={{ 
                        width: '8px', height: '8px', borderRadius: '50%', 
                        backgroundColor: market.is_active ? '#10b981' : '#cbd5e1',
                        boxShadow: market.is_active ? '0 0 4px rgba(16, 185, 129, 0.4)' : 'none'
                      }} title={market.is_active ? 'Active' : 'Inactive'} />
                    </div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      <span style={{ fontSize: '11px', fontWeight: 'bold', backgroundColor: '#e2e8f0', color: '#475569', padding: '2px 6px', borderRadius: '4px' }}>
                        {market.code}
                      </span>
                      <span style={{ fontSize: '12px', color: '#64748b' }}>
                        {market.region || 'No Region'}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* RIGHT PANE: MARKET DETAILS */}
        <div style={{ flex: 1, padding: '40px', overflowY: 'auto', backgroundColor: '#f8fafc' }}>
          {selectedMarket ? (
            <div style={{ maxWidth: '800px', margin: '0 auto' }}>
              
              {/* Detail Header */}
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '32px' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                    <h2 style={{ margin: 0, fontSize: '32px', color: '#0f172a' }}>{selectedMarket.name}</h2>
                    <span style={{ 
                      padding: '4px 10px', fontSize: '12px', borderRadius: '12px', fontWeight: 'bold',
                      backgroundColor: selectedMarket.is_active ? '#d1fae5' : '#fef2f2', 
                      color: selectedMarket.is_active ? '#065f46' : '#991b1b'
                    }}>
                      {selectedMarket.is_active ? 'Active Market' : 'Inactive'}
                    </span>
                  </div>
                  <div style={{ color: '#64748b', fontSize: '15px' }}>
                    System Code: <strong style={{ color: '#334155' }}>{selectedMarket.code}</strong>
                  </div>
                </div>
              </div>

              {/* Data Cards (Ready for you to add more rows later!) */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '32px' }}>
                <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                  <div style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 'bold', marginBottom: '4px' }}>Geographic Region</div>
                  <div style={{ fontSize: '16px', color: '#1e293b', fontWeight: '500' }}>{selectedMarket.region || 'Not Specified'}</div>
                </div>
                
                <div style={{ backgroundColor: 'white', padding: '20px', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                  <div style={{ fontSize: '12px', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 'bold', marginBottom: '4px' }}>Primary Language</div>
                  <div style={{ fontSize: '16px', color: '#1e293b', fontWeight: '500' }}>{selectedMarket.language || 'Not Specified'}</div>
                </div>
              </div>

              {/* Description Block */}
              <div style={{ backgroundColor: 'white', padding: '24px', borderRadius: '8px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                <h3 style={{ margin: '0 0 12px 0', fontSize: '16px', color: '#0f172a' }}>Market Description & Notes</h3>
                {selectedMarket.description ? (
                  <p style={{ margin: 0, color: '#475569', lineHeight: '1.6', fontSize: '14px' }}>
                    {selectedMarket.description}
                  </p>
                ) : (
                  <p style={{ margin: 0, color: '#94a3b8', fontStyle: 'italic', fontSize: '14px' }}>
                    No internal notes or description provided for this market.
                  </p>
                )}
              </div>

              <div style={{ marginTop: '24px', fontSize: '12px', color: '#94a3b8', textAlign: 'right' }}>
                Database ID: {selectedMarket.id}
              </div>

            </div>
          ) : (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8', fontSize: '18px' }}>
              Select a market from the list to view details.
            </div>
          )}
        </div>

      </div>
    </div>
  );
};

export default MarketView;