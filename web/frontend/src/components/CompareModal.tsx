import { useState, useEffect } from 'react';
import axios from 'axios';
import { API_BASE } from '../config';

interface Props { pnu1: string; pnu2: string; onClose: () => void; triggerBtnId?: string }
interface Apt {
  basic: { pnu: string; bld_nm: string; total_hhld_cnt?: number; dong_count?: number; max_floor?: number; use_apr_day?: string; new_plat_plc?: string };
  scores: Record<string, number>;
  facility_summary: Record<string, { nearest_distance_m: number; count_1km: number }>;
  school: { elementary_school_name?: string; middle_school_zone?: string; high_school_zone?: string } | null;
  safety?: { safety_score?: number; cctv_count_500m?: number } | null;
}

const NUDGES = [
  { id: 'cost', l: '가성비', i: '💰' }, { id: 'commute', l: '출퇴근', i: '🚇' },
  { id: 'education', l: '교육', i: '📚' }, { id: 'investment', l: '투자', i: '📈' },
  { id: 'newlywed', l: '신혼', i: '💑' }, { id: 'pet', l: '반려동물', i: '🐾' },
  { id: 'senior', l: '시니어', i: '🏥' }, { id: 'nature', l: '자연', i: '🌿' }, { id: 'safety', l: '안전', i: '🛡' },
];
const FACS = [
  { id: 'subway', l: '지하철' }, { id: 'bus_stop', l: '버스' },
  { id: 'hospital', l: '병원' }, { id: 'park', l: '공원' },
  { id: 'convenience_store', l: '편의점' }, { id: 'school', l: '학교' },
];

export default function CompareModal({ pnu1, pnu2, onClose, triggerBtnId }: Props) {
  const [show, setShow] = useState(false);
  const [a, setA] = useState<Apt | null>(null);
  const [b, setB] = useState<Apt | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!triggerBtnId) return;
    const el = document.getElementById(triggerBtnId);
    if (!el) return;
    const h = () => setShow(true);
    el.addEventListener('click', h);
    return () => el.removeEventListener('click', h);
  }, [triggerBtnId]);

  useEffect(() => {
    if (!show) return;
    setLoading(true);
    Promise.all([
      axios.get(`${API_BASE}/api/apartment/${encodeURIComponent(pnu1)}`),
      axios.get(`${API_BASE}/api/apartment/${encodeURIComponent(pnu2)}`),
    ]).then(([r1, r2]) => { setA(r1.data); setB(r2.data); })
      .catch(console.error).finally(() => setLoading(false));
  }, [pnu1, pnu2, show]);

  if (!show) return null;
  const close = () => { setShow(false); onClose(); };

  let wA = 0, wB = 0;
  if (a && b) NUDGES.forEach(n => {
    const sa = a.scores[n.id] ?? 0, sb = b.scores[n.id] ?? 0;
    if (sa > sb) wA++; else if (sb > sa) wB++;
  });

  return (
    <div onClick={e => { if (e.target === e.currentTarget) close(); }}
      style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.3)' }}>

      <div style={{
        width: 520, maxHeight: '82vh', margin: '0 12px',
        background: '#fff', borderRadius: 16, boxShadow: '0 20px 50px rgba(0,0,0,0.15)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid #f1f5f9' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 15, fontWeight: 700, color: '#1e293b' }}>아파트 비교</span>
            {a && b && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
                <span style={{ background: '#dbeafe', color: '#2563eb', fontWeight: 700, padding: '2px 6px', borderRadius: 4 }}>{wA}승</span>
                <span style={{ color: '#cbd5e1' }}>vs</span>
                <span style={{ background: '#ede9fe', color: '#7c3aed', fontWeight: 700, padding: '2px 6px', borderRadius: 4 }}>{wB}승</span>
              </div>
            )}
          </div>
          <button onClick={close} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', fontSize: 20, lineHeight: 1 }}>&times;</button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 16px 20px' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: '#94a3b8', fontSize: 14 }}>불러오는 중...</div>
          ) : a && b ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

              {/* 아파트 카드 */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div style={{ background: '#2563eb', color: '#fff', borderRadius: 10, padding: '12px 14px' }}>
                  <div style={{ fontSize: 10, fontWeight: 700, background: 'rgba(255,255,255,0.2)', display: 'inline-block', padding: '2px 6px', borderRadius: 4, marginBottom: 6 }}>A</div>
                  <div style={{ fontSize: 14, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.basic.bld_nm}</div>
                  <div style={{ fontSize: 11, opacity: 0.65, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.basic.new_plat_plc || '-'}</div>
                  <div style={{ fontSize: 11, opacity: 0.75, marginTop: 6, display: 'flex', gap: 6 }}>
                    <span>{a.basic.total_hhld_cnt ?? '-'}세대</span>
                    <span>·</span>
                    <span>{a.basic.max_floor ?? '-'}층</span>
                    <span>·</span>
                    <span>{fy(a.basic.use_apr_day)}</span>
                  </div>
                </div>
                <div style={{ background: '#7c3aed', color: '#fff', borderRadius: 10, padding: '12px 14px' }}>
                  <div style={{ fontSize: 10, fontWeight: 700, background: 'rgba(255,255,255,0.2)', display: 'inline-block', padding: '2px 6px', borderRadius: 4, marginBottom: 6 }}>B</div>
                  <div style={{ fontSize: 14, fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.basic.bld_nm}</div>
                  <div style={{ fontSize: 11, opacity: 0.65, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{b.basic.new_plat_plc || '-'}</div>
                  <div style={{ fontSize: 11, opacity: 0.75, marginTop: 6, display: 'flex', gap: 6 }}>
                    <span>{b.basic.total_hhld_cnt ?? '-'}세대</span>
                    <span>·</span>
                    <span>{b.basic.max_floor ?? '-'}층</span>
                    <span>·</span>
                    <span>{fy(b.basic.use_apr_day)}</span>
                  </div>
                </div>
              </div>

              {/* 라이프 점수 */}
              <div>
                <STitle>라이프 점수</STitle>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {NUDGES.map(n => {
                    const sa = a.scores[n.id] ?? 0, sb = b.scores[n.id] ?? 0;
                    const wA = sa > sb, wB = sb > sa;
                    return (
                      <div key={n.id} style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
                        {/* A score */}
                        <span style={{ width: 28, textAlign: 'right', fontSize: 13, fontWeight: wA ? 700 : 400, color: wA ? '#2563eb' : '#94a3b8', fontVariantNumeric: 'tabular-nums' }}>
                          {sa.toFixed(0)}
                        </span>
                        {/* A bar */}
                        <div style={{ flex: 1, height: 8, background: '#f1f5f9', borderRadius: 4, margin: '0 4px', display: 'flex', justifyContent: 'flex-end', overflow: 'hidden' }}>
                          <div style={{ width: `${Math.min(sa, 100)}%`, height: '100%', borderRadius: 4, background: wA ? '#3b82f6' : '#cbd5e1', transition: 'width 0.4s' }} />
                        </div>
                        {/* Label */}
                        <div style={{ width: 74, textAlign: 'center', fontSize: 12, color: '#64748b', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 3 }}>
                          <span>{n.i}</span><span>{n.l}</span>
                        </div>
                        {/* B bar */}
                        <div style={{ flex: 1, height: 8, background: '#f1f5f9', borderRadius: 4, margin: '0 4px', overflow: 'hidden' }}>
                          <div style={{ width: `${Math.min(sb, 100)}%`, height: '100%', borderRadius: 4, background: wB ? '#7c3aed' : '#cbd5e1', transition: 'width 0.4s' }} />
                        </div>
                        {/* B score */}
                        <span style={{ width: 28, fontSize: 13, fontWeight: wB ? 700 : 400, color: wB ? '#7c3aed' : '#94a3b8', fontVariantNumeric: 'tabular-nums' }}>
                          {sb.toFixed(0)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* 주변 시설 */}
              <div>
                <STitle>주변 시설</STitle>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid #e2e8f0' }}>
                      <th style={{ textAlign: 'left', padding: '6px 8px', color: '#64748b', fontWeight: 600, fontSize: 12 }}>시설</th>
                      <th style={{ textAlign: 'center', padding: '6px 8px', color: '#2563eb', fontWeight: 700, fontSize: 12, width: 80 }}>A</th>
                      <th style={{ textAlign: 'center', padding: '6px 8px', color: '#7c3aed', fontWeight: 700, fontSize: 12, width: 80 }}>B</th>
                    </tr>
                  </thead>
                  <tbody>
                    {FACS.map(f => {
                      const da = a.facility_summary[f.id]?.nearest_distance_m;
                      const db = b.facility_summary[f.id]?.nearest_distance_m;
                      const winA = da != null && db != null && da < db;
                      const winB = da != null && db != null && db < da;
                      return (
                        <tr key={f.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                          <td style={{ padding: '7px 8px', color: '#475569' }}>{f.l}</td>
                          <td style={{ padding: '7px 8px', textAlign: 'center', fontWeight: winA ? 700 : 400, color: winA ? '#2563eb' : '#94a3b8' }}>{fd(da)}</td>
                          <td style={{ padding: '7px 8px', textAlign: 'center', fontWeight: winB ? 700 : 400, color: winB ? '#7c3aed' : '#94a3b8' }}>{fd(db)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* 학군 + 안전 */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                {/* 학군 */}
                <div>
                  <STitle>학군</STitle>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: 12 }}>
                    <SchBox school={a.school} />
                    <SchBox school={b.school} />
                  </div>
                </div>
                {/* 안전 */}
                <div>
                  <STitle>안전</STitle>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                    <SafeBox s={a.safety?.safety_score ?? 0} c={a.safety?.cctv_count_500m ?? 0}
                      other={b.safety?.safety_score ?? 0} col="#2563eb" />
                    <SafeBox s={b.safety?.safety_score ?? 0} c={b.safety?.cctv_count_500m ?? 0}
                      other={a.safety?.safety_score ?? 0} col="#7c3aed" />
                  </div>
                </div>
              </div>

            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function STitle({ children }: { children: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
      <div style={{ width: 3, height: 14, borderRadius: 2, background: '#3b82f6' }} />
      <span style={{ fontSize: 13, fontWeight: 700, color: '#334155' }}>{children}</span>
    </div>
  );
}

function SchBox({ school }: { school: Apt['school'] }) {
  const s = { background: '#f8fafc', borderRadius: 8, padding: '10px 10px', color: '#475569', lineHeight: 1.6, display: 'flex', flexDirection: 'column', justifyContent: 'center', minHeight: 64 } as const;
  if (!school) return <div style={{ ...s, color: '#cbd5e1', textAlign: 'center', alignItems: 'center' }}>-</div>;
  return (
    <div style={s}>
      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        <span style={{ color: '#94a3b8', marginRight: 4 }}>초</span>{school.elementary_school_name || '-'}
      </div>
      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        <span style={{ color: '#94a3b8', marginRight: 4 }}>중</span>{school.middle_school_zone || '-'}
      </div>
      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        <span style={{ color: '#94a3b8', marginRight: 4 }}>고</span>{school.high_school_zone || '-'}
      </div>
    </div>
  );
}

function SafeBox({ s, c, other, col }: { s: number; c: number; other: number; col: string }) {
  const win = s > other;
  const ring = win ? '#10b981' : col;
  const r = 18, circ = 2 * Math.PI * r;
  return (
    <div style={{
      background: win ? '#ecfdf5' : '#f8fafc', borderRadius: 8, padding: '10px 10px',
      display: 'flex', alignItems: 'center', gap: 8,
      border: win ? '1px solid #a7f3d0' : '1px solid transparent',
    }}>
      <svg width="44" height="44" viewBox="0 0 44 44">
        <circle cx="22" cy="22" r={r} fill="none" stroke="#e2e8f0" strokeWidth="3" />
        <circle cx="22" cy="22" r={r} fill="none" stroke={ring} strokeWidth="3"
          strokeDasharray={`${(s / 100) * circ} ${circ}`}
          strokeLinecap="round" transform="rotate(-90 22 22)" />
        <text x="22" y="24" textAnchor="middle" fontSize="11" fontWeight="bold"
          fill={win ? '#059669' : '#64748b'}>{s.toFixed(0)}</text>
      </svg>
      <div>
        <div style={{ fontSize: 13, fontWeight: 700, color: win ? '#059669' : '#475569' }}>
          {s.toFixed(1)}{win && ' ✓'}
        </div>
        <div style={{ fontSize: 11, color: '#94a3b8' }}>CCTV {c}대</div>
      </div>
    </div>
  );
}

function fd(d?: number): string {
  if (d == null) return '-';
  const m = Math.round(d);
  return m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${m}m`;
}
function fy(d?: string): string {
  if (!d) return '-';
  return String(d).slice(0, 4) + '년';
}
