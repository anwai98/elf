import skimage.transform
# we use zarr here because z5py does not support nested directory for the zarr format
import zarr
from . import files

AXES_NAMES = {"t", "c", "z", "y", "x"}


def _get_chunks(ndim):
    return (256, 256) if ndim == 2 else (64, 64, 64)


def write_ome_zarr(data, path, name, n_scales,
                   key=None, chunks=None,
                   downscaler=skimage.transform.rescale,
                   kwargs={"scale": (0.5, 0.5, 0.5), "order": 0, "preserve_range": True}):
    """Write numpy data to ome.zarr format.
    """
    assert data.ndim in (2, 3)
    chunks = _get_chunks(data.ndim) if chunks is None else chunks
    axes_names = ["y", "x"] if data.ndim == 2 else ["z", "y", "x"]
    store = zarr.NestedDirectoryStore(path, dimension_separator="/")
    with zarr.open(store, mode='a') as f:
        g = f if key is None else f.require_group(key)
        g.create_dataset('s0', data=data, chunks=chunks, dimension_separator="/")
        if n_scales > 1:
            for ii in range(1, n_scales):
                data = downscaler(data, **kwargs).astype(data.dtype)
                g.create_dataset(f's{ii}', data=data, chunks=chunks, dimension_separator="/")
        function_name = f'{downscaler.__module__}.{downscaler.__name__}'
        create_ngff_metadata(g, name, axes_names,
                             type_=function_name, metadata=kwargs)


def create_ngff_metadata(g, name, axes_names, type_=None, metadata=None):
    """Create ome-ngff metadata for a multiscale dataset stored in zarr format.
    """
    assert files.is_z5py(g) or files.is_zarr(g)
    assert files.is_group(g)

    # validate the individual datasets
    ndim = g[list(g.keys())[0]].ndim
    assert all(dset.ndim == ndim for dset in g.values())
    assert all(files.is_dataset(dset) for dset in g.values())
    assert len(axes_names) == ndim
    assert len(set(axes_names) - AXES_NAMES) == 0

    ms_entry = {
        "datasets": [
            {"path": name} for name in g
        ],
        "axes": axes_names,
        "name": name,
        "version": "0.3"
    }
    if type_ is not None:
        ms_entry["type"] = type_
    if metadata is not None:
        ms_entry["metadata"] = metadata

    metadata = g.attrs.get("multiscales", [])
    metadata.append(ms_entry)
    g.attrs["multiscales"] = metadata
    g.attrs["_ARRAY_DIMENSIONS"] = axes_names