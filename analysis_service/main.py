from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import re
import os
from datetime import datetime

app = FastAPI(title='Analysis Service', version='1.0.0')

FILE_SERVICE_URL = os.getenv('FILE_SERVICE_URL', 'http://fileservice:80')

submissions_db = {}
reports_db = {}

K_SHINGLE_SIZE = 5
PLAGIARISM_THRESHOLD = 0.65


class AnalysisRequest(BaseModel):
    file_id: str
    student_id: str
    assignment_id: str


def normalize_code(code):
    # убираем комментарии
    code = re.sub(r'#.*', '', code)
    code = re.sub(r'//.*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

    # lowercase
    code = code.lower()

    # убираем лишние пробелы
    code = re.sub(r'\s+', ' ', code)
    code = code.strip()

    return code


def generate_shingles(code):
    # нормализуем код
    normalized = normalize_code(code)

    # разбиваем на слова
    tokens = normalized.split()

    # если слов меньше чем k, возвращаем весь код
    if len(tokens) < K_SHINGLE_SIZE:
        shingles = set()
        shingles.add(normalized)
        return shingles

    # генерируем шинглы
    shingles = set()
    i = 0
    while i <= len(tokens) - K_SHINGLE_SIZE:
        shingle = ''
        j = 0
        while j < K_SHINGLE_SIZE:
            if j > 0:
                shingle += ' '
            shingle += tokens[i + j]
            j += 1
        shingles.add(shingle)
        i += 1

    return shingles


def calculate_jaccard(set1, set2):
    # если оба пустые
    if len(set1) == 0 and len(set2) == 0:
        return 1.0

    # если один пустой
    if len(set1) == 0 or len(set2) == 0:
        return 0.0

    # пересечение
    intersection = 0
    for item in set1:
        if item in set2:
            intersection += 1

    # объединение
    union = len(set1) + len(set2) - intersection
    # находим отношение размера пересечения к количеству повторяющися слов без учета повторений
    result = intersection / union
    return round(result, 4)


def calculate_structural_similarity(metrics1, metrics2):
    # сравниваем размеры файлов
    size1 = metrics1['file_size']
    size2 = metrics2['file_size']
    max_size = size1 if size1 > size2 else size2
    if max_size == 0:
        max_size = 1

    size_diff = abs(size1 - size2)
    size_similarity = 1 - (size_diff / max_size)

    # сравниваем количество строк
    lines1 = metrics1['code_lines']
    lines2 = metrics2['code_lines']
    max_lines = lines1 if lines1 > lines2 else lines2
    if max_lines == 0:
        max_lines = 1

    lines_diff = abs(lines1 - lines2)
    lines_similarity = 1 - (lines_diff / max_lines)

    # среднее
    structural_sim = (size_similarity + lines_similarity) / 2.0
    return round(structural_sim, 4)


@app.post('/api/analysis')
async def analyze_work(request: AnalysisRequest):
    try:
        # генерируем id для работы
        work_id = 'work_' + str(len(submissions_db) + 1)

        # получаем файл из file service
        client = httpx.AsyncClient(timeout=30.0)

        content_response = await client.get(FILE_SERVICE_URL + '/api/files/' + request.file_id + '/content')

        if content_response.status_code != 200:
            await client.aclose()
            raise HTTPException(status_code=404, detail='File not found in FileService')

        code_content = content_response.json()['content']

        # получаем метрики
        metrics_response = await client.get(FILE_SERVICE_URL + '/api/files/' + request.file_id + '/metrics')
        metrics = metrics_response.json()

        await client.aclose()

        # генерируем шинглы для этого файла
        current_shingles = generate_shingles(code_content)

        # сохраняем работу
        submission = {
            'work_id': work_id,
            'student_id': request.student_id,
            'assignment_id': request.assignment_id,
            'file_id': request.file_id,
            'shingles': list(current_shingles),
            'metrics': metrics,
            'submission_date': datetime.now().isoformat()
        }
        submissions_db[work_id] = submission

        # ищем плагиат
        max_similarity = 0.0
        matched_work_id = None
        max_jaccard = 0.0
        max_structural = 0.0
        matched_shingles_count = 0

        for prev_work_id in submissions_db:
            prev_work = submissions_db[prev_work_id]

            # пропускаем саму работу
            if prev_work_id == work_id:
                continue

            # проверяем только работы по тому же заданию
            if prev_work['assignment_id'] != request.assignment_id:
                continue

            # считаем jaccard
            prev_shingles = set(prev_work['shingles'])
            jaccard_sim = calculate_jaccard(current_shingles, prev_shingles)

            # считаем структурное сходство
            structural_sim = calculate_structural_similarity(metrics, prev_work['metrics'])

            # комбинированный score
            combined_score = (jaccard_sim * 0.8) + (structural_sim * 0.2)

            if combined_score > max_similarity:
                max_similarity = combined_score
                matched_work_id = prev_work_id
                max_jaccard = jaccard_sim
                max_structural = structural_sim

                # считаем совпадающие шинглы
                matched_count = 0
                for shingle in current_shingles:
                    if shingle in prev_shingles:
                        matched_count += 1
                matched_shingles_count = matched_count

        # создаём отчёт
        report_id = 'report_' + work_id
        is_plagiarism = False
        if max_similarity > PLAGIARISM_THRESHOLD:
            is_plagiarism = True

        report = {
            'report_id': report_id,
            'work_id': work_id,
            'is_plagiarism': is_plagiarism,
            'similarity_score': round(max_similarity, 4),
            'jaccard_similarity': max_jaccard,
            'structural_similarity': max_structural,
            'matched_work_id': matched_work_id,
            'matched_shingles_count': matched_shingles_count,
            'analysis_date': datetime.now().isoformat()
        }

        reports_db[work_id] = report

        return {'work_id': work_id, 'message': 'Analysis completed successfully'}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Analysis failed: {str(e)}')


@app.get('/api/analysis/{work_id}/report')
async def get_report(work_id):
    if work_id not in reports_db:
        raise HTTPException(status_code=404, detail='Report not found')

    return reports_db[work_id]


@app.get('/health')
async def health_check():
    return {'status': 'healthy', 'service': 'analysis-service'}


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=5002)
