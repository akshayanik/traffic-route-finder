import math
import pydeck as pdk
import streamlit as st
from streamlit_searchbox import st_searchbox
from routes import get_routes, analyze_routes, rank_routes, format_time, suggest_places

# One colour per route, matching the pink theme: hot pink, lavender, peach
ROUTE_COLORS = [[236, 72, 153], [168, 85, 247], [251, 146, 60]]
LABEL_EMOJI = {"Clear": "🟢", "Moderate": "🟡", "Heavy": "🔴"}

st.set_page_config(page_title="Least-Traffic Route Finder", page_icon="🌸")

st.title("🌸 Least-Traffic Route Finder")
st.write("Find the calmest route, not just the fastest one.")


def show_map(ranked):
    paths = []
    all_points = []
    for i, r in enumerate(ranked):
        if r["path"]:
            paths.append({
                "name": f"{i + 1}. via {r['name']}",
                "path": r["path"],
                "color": ROUTE_COLORS[i % len(ROUTE_COLORS)],
            })
            all_points.extend(r["path"])

    if not all_points:
        return

    # Centre the map on the routes and zoom to fit them
    lngs = [p[0] for p in all_points]
    lats = [p[1] for p in all_points]
    span = max(max(lats) - min(lats), max(lngs) - min(lngs), 0.01)
    zoom = max(3, min(13, 9 - math.log2(span)))

    view = pdk.ViewState(
        latitude=(max(lats) + min(lats)) / 2,
        longitude=(max(lngs) + min(lngs)) / 2,
        zoom=zoom,
    )
    layer = pdk.Layer(
        "PathLayer",
        data=list(reversed(paths)),  # draw the best route last, so it sits on top
        get_path="path",
        get_color="color",
        width_min_pixels=5,
        pickable=True,
    )
    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        map_provider="carto",
        map_style=pdk.map_styles.CARTO_LIGHT,
        tooltip={"text": "{name}"},
    ))


origin = st_searchbox(
    suggest_places,
    label="Starting point",
    placeholder="Start typing a place...",
    key="origin",
    debounce=400,
)
destination = st_searchbox(
    suggest_places,
    label="Destination",
    placeholder="Start typing a place...",
    key="destination",
    debounce=400,
)

if st.button("Find routes", type="primary"):
    if not origin or not destination:
        st.warning("Please enter both a starting point and a destination.")
    else:
        with st.spinner("Checking live traffic..."):
            results = analyze_routes(get_routes(origin, destination))

        if not results:
            st.error("No routes found. Check the place names and try again.")
        else:
            ranked = rank_routes(results)
            fastest = min(results, key=lambda r: r["with_traffic"])
            calmest = ranked[0]

            if calmest is fastest:
                st.success(f"Good news: the fastest route, via {fastest['name']}, also has the least traffic! 💖")
            elif fastest["label"] == "Clear":
                st.success(
                    f"Traffic is light on every route, so just take the fastest one: "
                    f"via {fastest['name']} ({format_time(fastest['with_traffic'])})."
                )
            else:
                extra = calmest["with_traffic"] - fastest["with_traffic"]
                avoided = fastest["delay"] - calmest["delay"]
                st.info(
                    f"The fastest route (via {fastest['name']}) has {format_time(fastest['delay'])} of traffic. "
                    f"The calmest route (via {calmest['name']}) avoids about {format_time(avoided)} of it, "
                    f"for {format_time(extra)} extra overall."
                )

            show_map(ranked)

            st.subheader("Routes ranked by least time in traffic")
            for i, r in enumerate(ranked):
                color = ROUTE_COLORS[i % len(ROUTE_COLORS)]
                with st.container(border=True):
                    st.markdown(
                        f"<span style='color:rgb({color[0]},{color[1]},{color[2]}); font-size:1.4em'>●</span> "
                        f"**{i + 1}. via {r['name']}**",
                        unsafe_allow_html=True,
                    )
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Time right now", format_time(r["with_traffic"]))
                    col2.metric("Stuck in traffic", format_time(r["delay"]))
                    col3.metric("Distance", f"{r['km']:.0f} km")
                    st.progress(
                        min(r["congestion"] / 50, 1.0),
                        text=f"{LABEL_EMOJI[r['label']]} Congestion: {r['congestion']:.0f}% ({r['label']})",
                    )