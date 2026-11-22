"""Public-file Docker bind probe; never mount or read account credentials."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

import docker


def probe(parent):
    parent = Path(parent).resolve(strict=True)
    evidence = parent / str(uuid4())
    evidence.mkdir()
    controller = evidence / ('controller-' + uuid4().hex)
    controller.mkdir()
    view = controller / 'view'
    view.mkdir()
    config = controller / 'config.json'
    config.write_text('{}', encoding='utf-8')
    client = docker.from_env()
    try:
        output = client.containers.run(
            'laomedo-opencode:1.18.33',
            ['-c', "import os; print(os.stat('/controller-config.json').st_size); print(os.stat('/draft').st_mode)"],
            entrypoint='python3', network_mode='none', remove=True,
            mounts=[docker.types.Mount('/controller-config.json', str(config), type='bind', read_only=True), docker.types.Mount('/draft', str(view), type='bind', read_only=True)],
        )
        return {'source_length': len(str(config)), 'readable': True, 'metadata': output.decode().splitlines()}
    except docker.errors.ContainerError as error:
        return {'source_length': len(str(config)), 'readable': False, 'exit_status': error.exit_status}
    finally:
        client.close()
        if controller.is_symlink() or not controller.resolve().is_relative_to(parent):
            raise RuntimeError('Probe cleanup path changed')
        config.unlink()
        view.rmdir()
        controller.rmdir()
        evidence.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog_parent', type=Path)
    parser.add_argument('profile_parent', type=Path)
    args = parser.parse_args()
    print(json.dumps({'catalog': probe(args.catalog_parent), 'profile': probe(args.profile_parent)}))


if __name__ == '__main__':
    main()