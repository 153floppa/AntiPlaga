from fastapi import FastAPI, UploadFile, File, Form, HTTPException
import httpx
import os

app = FastAPI(title='API Gateway', version='1.0.0')

FILE_SERVICE_URL = os.getenv('FILE_SERVICE_URL', 'http://fileservice:80')
ANALYSIS_SERVICE_URL = os.getenv('ANALYSIS_SERVICE_URL', 'http://analysisservice:80')


@app.post('/works')
async def submit_work(file: UploadFile = File(...), student_id=Form(...), assignment_id=Form(...)):
    try: #UploadFile сделал тк в свагере не работала загрузка файла
        client = httpx.AsyncClient(timeout=60.0)

        # загружаем файл
        file_content = await file.read()
        files = {'file': (file.filename, file_content, file.content_type)}
        # тут прямо к апишке файл сервиса обращаемся и грузим соответственно
        file_response = await client.post(FILE_SERVICE_URL + '/api/files', files=files)
        if file_response.status_code != 200:
            await client.aclose() # проверяем норм ли загрузило
            raise HTTPException(status_code=file_response.status_code, detail='Failed to upload file')

        file_data = file_response.json()
        file_id = file_data['file_id']

        # запускаем анализ
        analysis_payload = {
            'file_id': file_id,
            'student_id': student_id,
            'assignment_id': assignment_id
        }

        analysis_response = await client.post(ANALYSIS_SERVICE_URL + '/api/analysis', json=analysis_payload)

        if analysis_response.status_code != 200:
            await client.aclose() # проверяем, что анализ прошел без косяков
            raise HTTPException(status_code=analysis_response.status_code, detail='Failed to start analysis')

        result = analysis_response.json()
        await client.aclose()

        return {
            'work_id': result['work_id'],
            'file_id': file_id,
            'message': 'Work submitted successfully',
            'student_id': student_id,
            'assignment_id': assignment_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Submission failed: {str(e)}')


@app.get('/works/{work_id}/reports')
async def get_report(work_id):
    try:
        client = httpx.AsyncClient(timeout=30.0)

        response = await client.get(ANALYSIS_SERVICE_URL + '/api/analysis/' + work_id + '/report')

        if response.status_code == 404:
            await client.aclose()
            raise HTTPException(status_code=404, detail='Report not found')

        if response.status_code != 200:
            await client.aclose()
            raise HTTPException(status_code=response.status_code, detail='Failed to fetch report')

        report = response.json()
        await client.aclose()

        return report

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to get report: {str(e)}')


@app.get('/health')
async def health_check():
    services_status = {'gateway': 'healthy'}

    try:
        client = httpx.AsyncClient(timeout=5.0)

        # проверяем file service
        try:
            fs_response = await client.get(FILE_SERVICE_URL + '/health')
            if fs_response.status_code == 200:
                services_status['file_service'] = 'healthy'
            else:
                services_status['file_service'] = 'unhealthy'
        except:
            services_status['file_service'] = 'unavailable'

        # проверяем analysis service
        try:
            as_response = await client.get(ANALYSIS_SERVICE_URL + '/health')
            if as_response.status_code == 200:
                services_status['analysis_service'] = 'healthy'
            else:
                services_status['analysis_service'] = 'unhealthy'
        except:
            services_status['analysis_service'] = 'unavailable'

        await client.aclose()
    except:
        pass

    return services_status


if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host='0.0.0.0', port=5000)
