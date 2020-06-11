import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
import yaml
import xarray as xr
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
from base64 import b64encode

border_time = np.timedelta64(3, "m")

env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates')),
    autoescape=select_autoescape(['html', 'xml'])
)

def fig2data_url(fig):
    io = BytesIO()
    fig.savefig(io, format="PNG", bbox_inches="tight")
    b64 = b64encode(io.getvalue())
    url = "data:{};base64,{}".format("image/png", b64.decode("ascii"))
    return url

def start_end_lims(bahamas):
    lat_min = min(*bahamas.lat.data[[0,-1]])
    lat_max = max(*bahamas.lat.data[[0,-1]])
    lon_min = min(*bahamas.lon.data[[0,-1]])
    lon_max = max(*bahamas.lon.data[[0,-1]])
    delta = ((lat_max - lat_min) ** 2 + (lon_max - lon_min) ** 2)**.5
    lat_center = (lat_min + lat_max) / 2
    lon_center = (lon_min + lon_max) / 2
    return (lat_center - delta, lat_center + delta), (lon_center - delta, lon_center + delta)

def default_segment_plot(seg, sonde_track, seg_before, seg_after):
    fig, (overview_ax, roll_ax) = plt.subplots(2, figsize=(6,6))
    overview_ax.plot(seg.lon, seg.lat, zorder=10)
    overview_ax.plot(seg_before.lon, seg_before.lat, color="C3", alpha=.3, zorder=0)
    overview_ax.plot(seg_after.lon, seg_after.lat, color="C3", alpha=.3, zorder=0)
    overview_ax.scatter(sonde_track.lon, sonde_track.lat, color="C1", zorder=5)


    seg["roll"].plot(ax=roll_ax, zorder=10)
    seg_before["roll"].plot(ax=roll_ax, color="C3", alpha=.3, zorder=0)
    seg_after["roll"].plot(ax=roll_ax, color="C3", alpha=.3, zorder=0)

    return fig

def circle_detail_plot(seg, sonde_track, seg_before, seg_after):
    fig, zoom_ax = plt.subplots(1, figsize=(4,4))
    zoom_ax.plot(seg.lon, seg.lat, "o-", zorder=10)
    zoom_ax.plot(seg_before.lon, seg_before.lat, "x-", color="C3", alpha=.3, zorder=0)
    zoom_ax.plot(seg_after.lon, seg_after.lat, "x-", color="C3", alpha=.3, zorder=0)

    zoom_ax.scatter(sonde_track.lon, sonde_track.lat, color="C1", zorder=5)
    lat_lims, lon_lims = start_end_lims(seg)
    zoom_ax.set_xlim(*lon_lims)
    zoom_ax.set_ylim(*lat_lims)
    zoom_ax.set_aspect("equal")
    zoom_ax.set_title("zoom on circle ends")

    return fig

SPECIAL_PLOTS = {
    "circle": [circle_detail_plot],
}

def plots_for_kinds(kinds):
    return [default_segment_plot] + \
           [plot
            for kind in kinds
            for plot in SPECIAL_PLOTS.get(kind, [])]

def _main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("infile")
    parser.add_argument("outfile")
    parser.add_argument("-d", "--data_path", default="../data")
    args = parser.parse_args()

    flightdata = yaml.load(open(args.infile), Loader=yaml.SafeLoader)
    bahamas_path = os.path.join(args.data_path,
                                "bahamas_{:%Y%m%d}_v0.4.nc".format(flightdata["date"]))
    dropsondes_path = os.path.join(args.data_path,
                                   "dropsondes_{:%Y%m%d}_v0.4.nc".format(flightdata["date"]))
    bahamas = xr.open_dataset(bahamas_path)
    dropsondes = xr.open_dataset(dropsondes_path)

    data_info = {
        "first_sonde": dropsondes.launch_time.data[0]
    }

    fig, ax = plt.subplots()
    ax.plot(bahamas.lon, bahamas.lat)
    im = fig2data_url(fig)
    plt.close("all")
    flightdata["plot_data"] = im
    flightdata["data_info"] = data_info

    for seg in flightdata["segments"]:
        sonde_mask = (dropsondes.launch_time.data >= np.datetime64(seg["start"])) \
                   & (dropsondes.launch_time.data < np.datetime64(seg["end"]))
        sondes = dropsondes.isel(sonde_number=sonde_mask)
        t_start = np.datetime64(seg["start"])
        t_end = np.datetime64(seg["end"])
        seg_bahamas = bahamas.sel(time=slice(t_start, t_end))
        seg_before = bahamas.sel(time=slice(t_start - border_time, t_start))
        seg_after = bahamas.sel(time=slice(t_end, t_end + border_time))
        sonde_track = bahamas.sel(time=sondes.launch_time, method="nearest")

        plot_data = []
        for plot in plots_for_kinds(seg.get("kinds", [])):
            plot_data.append(fig2data_url(
                plot(seg_bahamas, sonde_track, seg_before, seg_after)))
            plt.close("all")

        seg["plot_data"] = plot_data
        seg["sonde_count_in_data"] = len(sondes.launch_time)
        seg["sonde_times"] = sondes.launch_time.data

    tpl = env.get_template("flight.html")

    with open(args.outfile, "w") as outfile:
        outfile.write(tpl.render(flight=flightdata))

if __name__ == "__main__":
    _main()
