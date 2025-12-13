from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import os
import uuid
from datetime import datetime

app = FastAPI(title='File Service', version='1.0.0')

STORAGE_PATH = os.getenv('STORAGE_PATH', './file_service/storage')
os.makedirs(STORAGE_PATH, exist_ok=True)

files_db = {}


def analyze_structure(content):
    # считаем строки кода и комментариев
    lines = content.split('\n')
    total_lines = len(lines)
    code_lines = 0
    comment_lines = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('#') or stripped.startswith('//') or stripped.startswith('/*'):
            comment_lines += 1
        else:
            code_lines += 1

    if code_lines > 0:
        comment_ratio = round(comment_lines / code_lines, 3)
    else:
        comment_ratio = 0.0

    return {
        'total_lines': total_lines,
        'code_lines': code_lines,
        'comment_lines': comment_lines,
        'comment_ratio': comment_ratio
    }


@app.post('/api/files')
async def upload_file(file=File(...)):
    try:
        file_id = str(uuid.uuid4())
        file_path = os.path.join(STORAGE_PATH, file_id)

        # читаем файл
        content = await file.read()
        file_size = len(content)

        # сохраняем на диск
        f = open(file_path, 'wb')
        f.write(content)
        f.close()

        # декодируем в текст
        try:
            content_str = content.decode('utf-8')
        except:
            content_str = content.decode('utf-8', errors='ignore')

        # анализируем структуру
        metrics = analyze_structure(content_str)

        # сохраняем метаданные
        metadata = {
            'file_id': file_id,
            'file_name': file.filename,
            'file_size': file_size,
            'file_path': file_path,
            'upload_date': datetime.now().isoformat(),
            'total_lines': metrics['total_lines'],
            'code_lines': metrics['code_lines'],
            'comment_lines': metrics['comment_lines'],
            'comment_ratio': metrics['comment_ratio']
        }

        files_db[file_id] = metadata
        return metadata

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'File upload failed: {str(e)}')


@app.get('/api/files/{file_id}')
async def download_file(file_id):
    if file_id not in files_db:
        raise HTTPException(status_code=404, detail='File not found')

    file_path = files_db[file_id]['file_path']

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail='File not found on disk')

    return FileResponse(file_path, media_type='application/octet-stream', filename=files_db[file_id]['file_name'])


@app.get('/api/files/{file_id}/content')
async def get_file_content(file_id):
    if file_id not in files_db:
        raise HTTPException(status_code=404, detail='File not found')

    file_path = files_db[file_id]['file_path']

    try:
        f = open(file_path, 'r', encoding='utf-8')
        content = f.read()
        f.close()
        return {'content': content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to read file: {str(e)}')


@app.get('/api/files/{file_id}/metrics')
async def get_file_metrics(file_id):
    if file_id not in files_db:
        raise HTTPException(status_code=404, detail='File not found')

    metadata = files_db[file_id]
    return {
        'file_size': metadata['file_size'],
        'total_lines': metadata['total_lines'],
        'code_lines': metadata['code_lines'],
        'comment_lines': metadata['comment_lines'],
        'comment_ratio': metadata['comment_ratio']
    }


@app.get('/health')
async def health_check():
    return {'status': 'healthy', 'service': 'file-service'}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=5001)
