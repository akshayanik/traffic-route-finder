import altair as alt
import pandas as pd
import math
import pydeck as pdk
import streamlit as st
from streamlit_searchbox import st_searchbox
from routes import (
    get_routes, analyze_routes, add_costs, find_badges,
    format_time, suggest_places,
)

# One colour per route, matching the pink theme: hot pink, lavender, peach
ROUTE_COLORS = [[236, 72, 153], [168, 85, 247], [251, 146, 60]]
LABEL_EMOJI = {"Clear": "🟢", "Moderate": "🟡", "Heavy": "🔴"}
DEFAULT_PRICES = {"Petrol": 100.0, "Diesel": 90.0}
EMISSION_TYPES = {"Petrol": "GASOLINE", "Diesel": "DIESEL"}

st.set_page_config(page_title="Route Finder", page_icon="🌸")

st.title("🌸 Least-Traffic Route Finder")
st.write("Compare routes by time, cost, distance and traffic, then pick what matters to you.")


def show_map(routes):
    paths = [
        {"name": f"via {r['name']}", "path": r["path"], "color": r["color"]}
        for r in routes if r["path"]
    ]
    all_points = [p for item in paths for p in item["path"]]
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
        data=paths,
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


# ---------- Inputs ----------
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

fuel_type = st.radio("Fuel type", ["Petrol", "Diesel"], horizontal=True)

col1, col2, col3 = st.columns(3)
smooth_mileage = col1.number_input("🟢 Mileage, smooth traffic (km/l)", min_value=1.0, value=18.0, step=0.5)
slow_mileage = col2.number_input("🟠🔴 Mileage, slow traffic (km/l)", min_value=1.0, value=10.0, step=0.5)
fuel_price = col3.number_input(
    f"{fuel_type} price (₹/litre)",
    min_value=1.0,
    value=DEFAULT_PRICES[fuel_type],
    step=1.0,
    key=f"price_{fuel_type}",
)
st.caption(
    "Smooth traffic is green on Google Maps; slow traffic is orange and red. "
    "Set the fuel price for your city, since it varies from place to place."
)

if st.button("Find routes", type="primary"):
    if not origin or not destination:
        st.warning("Please choose both a starting point and a destination.")
    else:
        with st.spinner("Checking live traffic and tolls..."):
            results = analyze_routes(get_routes(origin, destination, EMISSION_TYPES[fuel_type]))

        if not results:
            st.error("No routes found. Check the place names and try again.")
            st.session_state.pop("results", None)
        else:
            # Give each route a fixed colour so the map and cards always match
            for i, r in enumerate(results):
                r["color"] = ROUTE_COLORS[i % len(ROUTE_COLORS)]
            st.session_state["results"] = results


# ---------- Results ----------
results = st.session_state.get("results")

if results:
    add_costs(results, smooth_mileage, slow_mileage, fuel_price)
    picks = find_badges(results)

    st.subheader("At a glance")
    for badge, r in picks.items():
        st.markdown(
            f"**{badge}:** via {r['name']} · {format_time(r['with_traffic'])} · "
            f"{r['km']:.0f} km · ₹{r['total_cost']:,.0f}"
        )

    fastest = picks["⚡ Fastest"]
    cheapest = picks["💰 Cheapest"]
    if fastest is cheapest:
        st.success("The fastest route is also the cheapest. 💖")
    else:
        saved = fastest["total_cost"] - cheapest["total_cost"]
        extra = cheapest["with_traffic"] - fastest["with_traffic"]
        st.info(
            f"The cheapest route saves about ₹{saved:,.0f}, "
            f"but takes {format_time(extra)} longer than the fastest. "
            f"Save time or save money? Your call! 💖"
        )

    if any(not r["toll_known"] for r in results):
        st.caption("Some routes have tolls without a known price, so their real cost may be higher than shown.")

        tab_map, tab_chart, tab_table = st.tabs(["🗺️ Map", "📊 Chart", "📋 Table"])

    with tab_map:
        show_map(results)

    with tab_chart:
        chart_data = pd.DataFrame([{
            "Route": f"via {r['name']}",
            "Time (min)": round(r["with_traffic"]),
            "Cost (₹)": round(r["total_cost"]),
            "Distance (km)": round(r["km"], 1),
            "Badges": " ".join(r["badges"]),
            "color": f"rgb({r['color'][0]},{r['color'][1]},{r['color'][2]})",
        } for r in results])

        chart = alt.Chart(chart_data).mark_circle(size=400).encode(
            x=alt.X("Time (min):Q", scale=alt.Scale(zero=False)),
            y=alt.Y("Cost (₹):Q", scale=alt.Scale(zero=False)),
            color=alt.Color("color:N", scale=None),
            tooltip=["Route", "Badges", "Time (min)", "Cost (₹)", "Distance (km)"],
        )
        st.altair_chart(chart)
        st.caption("Each dot is a route, in the same colour as on the map. Further left is quicker, lower down is cheaper. Hover over a dot for details.")

    with tab_table:
        table = pd.DataFrame([{
            "Route": f"via {r['name']}",
            "Badges": " ".join(r["badges"]),
            "Time": format_time(r["with_traffic"]),
            "In traffic": format_time(r["delay"]),
            "Distance (km)": round(r["km"], 1),
            "Fuel (₹)": round(r["fuel_cost"]),
            "Tolls (₹)": f"{r['toll']:.0f}" if r["toll_known"] else "unknown",
            "Total (₹)": round(r["total_cost"]),
        } for r in results])
        st.dataframe(table, hide_index=True)

    sort_by = st.radio(
        "Sort routes by",
        ["Fastest", "Cheapest", "Shortest", "Calmest"],
        horizontal=True,
    )
    sort_keys = {
        "Fastest": lambda r: r["with_traffic"],
        "Cheapest": lambda r: r["total_cost"],
        "Shortest": lambda r: r["km"],
        "Calmest": lambda r: (round(r["delay"]), r["with_traffic"]),
    }

    for r in sorted(results, key=sort_keys[sort_by]):
        color = r["color"]
        toll_text = f"₹{r['toll']:,.0f}" if r["toll_known"] else "price unknown"

        with st.container(border=True):
            badges = "  ".join(r["badges"])
            st.markdown(
                f"<span style='color:rgb({color[0]},{color[1]},{color[2]}); font-size:1.4em'>●</span> "
                f"**via {r['name']}** &nbsp; {badges}",
                unsafe_allow_html=True,
            )
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Time now", format_time(r["with_traffic"]))
            c2.metric("In traffic", format_time(r["delay"]))
            c3.metric("Distance", f"{r['km']:.0f} km")
            c4.metric("Est. cost", f"₹{r['total_cost']:,.0f}")

            st.caption(
                f"🟢 {r['smooth_km']:.1f} km smooth · "
                f"🟠 {r['slow_km']:.1f} km slow · "
                f"🔴 {r['jam_km']:.1f} km jammed"
            )
            st.progress(
                min(r["congestion"] / 50, 1.0),
                text=f"{LABEL_EMOJI[r['label']]} Congestion: {r['congestion']:.0f}% ({r['label']})",
            )

            with st.expander("💰 Cost breakup"):
                st.write(
                    f"🟢 Fuel in smooth traffic: **₹{r['fuel_smooth']:,.0f}** "
                    f"({r['smooth_km']:.1f} km ÷ {smooth_mileage:g} km/l × ₹{fuel_price:g})"
                )
                st.write(
                    f"🟠🔴 Fuel in slow traffic: **₹{r['fuel_slow']:,.0f}** "
                    f"({r['slow_km'] + r['jam_km']:.1f} km ÷ {slow_mileage:g} km/l × ₹{fuel_price:g})"
                )
                st.write(f"⛽ Total fuel: **₹{r['fuel_cost']:,.0f}**")
                st.write(f"🛣️ Tolls: **{toll_text}**")
                st.write(f"💰 Total: **₹{r['total_cost']:,.0f}**")