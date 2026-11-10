"""HOT100 그래프 표본(써클 2026-11-06 01:00 글, 5곡 x 20시간)으로 점수 통계를 내고 예측 방식별 오차를 비교한다."""
import statistics as st
S = {
 "With":[7.0]*19+[6.823],
 "백화요란":[5.743,5.75,6.709,6.108,5.789,5.328,5.192,5.242,5.162,5.074,5.163,5.235,5.775,5.779,5.512,5.689,5.386,5.854,5.745,5.541],
 "Finest":[4.722,4.58,6.026,4.748,4.192,4.208,3.96,3.876,3.944,3.93,3.955,3.645,3.972,3.07,3.907,4.06,4.239,4.349,4.304,4.473],
 "MEME":[4.483,4.257,4.28,4.51,4.072,3.735,3.602,3.729,3.712,3.693,3.773,3.645,3.972,3.07,3.907,4.06,4.001,4.151,4.222,4.358],
 "Dragon":[4.395,4.098,3.601,3.372,3.774,3.804,3.245,3.578,3.589,3.542,3.498,3.465,3.621,3.518,3.843,3.902,3.889,3.986,4.222,4.219]}
names=list(S); T=len(S["With"])
# 시간대별 순위(점수 내림차순)
rk=[{n:r+1 for r,n in enumerate(sorted(names,key=lambda n:-S[n][t]))} for t in range(T)]
print("순위별 점수 통계(전 시간대):")
byrank={k:[S[n][t] for t in range(T) for n in names if rk[t][n]==k] for k in range(1,6)}
for k,v in byrank.items(): print(f" {k}위 중앙값 {st.median(v):.3f} 평균 {st.mean(v):.3f} 표준편차 {st.pstdev(v):.3f} 최소 {min(v)} 최대 {max(v)}")
print("\n순위 간 비율(해당 시간대 직전 순위 대비) 중앙값:")
for k in range(2,6):
    r=[S[n][t]/S[m][t] for t in range(T) for n in names for m in names if rk[t][n]==k and rk[t][m]==k-1]
    print(f" {k}위/{k-1}위 {st.median(r):.3f} (범위 {min(r):.2f}~{max(r):.2f})")
# 다음 시간 예측: 곡별 직전값 / 순위 중앙값 / 둘의 평균, 첫 시간대는 제외, leave-one-hour-out
def mae(f):
    e=[];m=[]
    for t in range(1,T):
        for n in names:
            p=f(n,t); a=S[n][t]; e.append(abs(p-a)); m.append(abs(p-a)/a)
    return st.mean(e), st.mean(m), max(m)
def med_rank(n,t):
    v=[S[x][u] for u in range(T) if u!=t for x in names if rk[u][x]==rk[t][n]]
    return st.median(v)
persist=lambda n,t:S[n][t-1]
blend=lambda n,t:0.5*persist(n,t)+0.5*min(7.0,med_rank(n,t))
w=lambda a:(lambda n,t:a*persist(n,t)+(1-a)*med_rank(n,t))
print("\n예측 오차 (평균절대오차 / 평균% / 최대%):")
for lab,f in [("직전값 유지",persist),("순위 중앙값(그 시간 순위 안다고 가정)",med_rank),("두 방식 평균",blend)]+[(f"직전값 {a:.1f} + 순위 {1-a:.1f}",w(a)) for a in (0.3,0.7)]:
    a,b,c=mae(f); print(f" {lab:34s} {a:.3f} / {b*100:.1f}% / {c*100:.0f}%")
